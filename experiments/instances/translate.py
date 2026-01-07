# pylint: disable=missing-docstring
import csv
import dataclasses
import gzip
import io
import itertools
import json
import math
import multiprocessing
import os
import pathlib
import statistics
import time
from types import ModuleType
from typing import List, Sequence

import aas_core3_protobuf.pbization
import ifcopenshell
import tqdm
from aas_core3 import (
    jsonization as aas_jsonization,
    xmlization as aas_xmlization,
    types as aas_types,
)
from icontract import ensure, require

import experiments.instances.IFC2X3  # pylint: disable=import-error,no-member
import experiments.instances.IFC4  # pylint: disable=import-error,no-member,no-name-in-module
import experiments.instances.IFC4X3_ADD2  # pylint: disable=import-error,no-member


class _ByteCounter:
    def __init__(self) -> None:
        self._count = 0

    def write(self, data: bytes) -> None:
        self._count += len(data)

    @property
    def count(self) -> int:
        return self._count

    def flush(self) -> None:
        pass


class ByteCounter:
    def __init__(self) -> None:
        self._uncompressed_counter = _ByteCounter()
        self._gzip_counter = _ByteCounter()

        # noinspection PyTypeChecker
        self._gzip = gzip.GzipFile(fileobj=self._gzip_counter, mode="wb")

        self._closed = False
        self._writable = True

    @property
    def closed(self) -> bool:
        return self._closed

    def writable(self) -> bool:
        return self._writable

    @property
    def count(self) -> int:
        return self._uncompressed_counter.count

    @property
    def gzip_count(self) -> int:
        return self._gzip_counter.count

    def close(self) -> None:
        self._gzip.close()
        self._closed = True
        self._writable = False

    def __enter__(self) -> "ByteCounter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def write(self, data: bytes) -> int:
        self._uncompressed_counter.write(data)
        self._gzip.write(data)

        return len(data)

    def flush(self) -> None:
        self._gzip.flush()

    # noinspection PyMethodMayBeStatic
    def readable(self) -> bool:
        return False

    # noinspection PyMethodMayBeStatic
    def seekable(self) -> bool:
        return False


@dataclasses.dataclass
class Outcome:
    submodel_count: int = 0
    json_count: int = 0
    json_gzip_count: int = 0
    xml_count: int = 0
    xml_gzip_count: int = 0
    protobuf_count: int = 0
    protobuf_gzip_count: int = 0
    submodel_json_sizes: List[float] = dataclasses.field(default_factory=list)

    def __add__(self, other: "Outcome") -> "Outcome":
        return Outcome(
            submodel_count=self.submodel_count + other.submodel_count,
            json_count=self.json_count + other.json_count,
            json_gzip_count=self.json_gzip_count + other.json_gzip_count,
            xml_count=self.xml_count + other.xml_count,
            xml_gzip_count=self.xml_gzip_count + other.xml_gzip_count,
            protobuf_count=self.protobuf_count + other.protobuf_count,
            protobuf_gzip_count=self.protobuf_gzip_count + other.protobuf_gzip_count,
            submodel_json_sizes=self.submodel_json_sizes + other.submodel_json_sizes,
        )


class Chunk:
    """Represent an immutable chunk of a range [start, end)."""

    @require(lambda start, end: 0 <= start < end)
    def __init__(self, start: int, end: int) -> None:
        self._start = start
        self._end = end

    @property
    def start(self) -> int:
        return self._start

    @property
    def end(self) -> int:
        return self._end

    def __repr__(self) -> str:
        return f"Chunk(start={self.start}, end={self.end})"


# fmt: off
@ensure(
    lambda total_count, result:
    (total_count == 0 and len(result) == 0)
    or (
            total_count != 0
            and len(result) > 0
            and result[0].start == 0
            and result[-1].end == total_count
            and all(
        previous_chunk.end == current_chunk.start
        for previous_chunk, current_chunk in itertools.pairwise(result)
    )
    )
)
# fmt: on
def compute_chunk_indices(total_count: int, num_chunks: int) -> List[Chunk]:
    chunk_size = total_count // num_chunks
    remainder = total_count % num_chunks

    chunks = []
    start = 0
    for i in range(num_chunks):
        # NOTE (mristin):
        # We add 1 to chunk_size for the first 'remainder' chunks.
        current_chunk_size = chunk_size + (1 if i < remainder else 0)
        end = start + current_chunk_size
        chunks.append(Chunk(start, end))
        start = end

    return chunks


@dataclasses.dataclass
class ChunkArgs:
    model_path: pathlib.Path
    chunk: Chunk
    # noinspection PyTypeHints
    progress_counter: multiprocessing.Value
    total_instances: int


def process_chunk(args: ChunkArgs) -> Outcome:
    start_idx, end_idx = args.chunk.start, args.chunk.end

    # Load model in each process
    model = ifcopenshell.open(str(args.model_path))

    # Determine module based on schema
    to_aas_module: ModuleType
    if model.schema == "IFC4":
        to_aas_module = experiments.instances.IFC4  # pylint: disable=no-member
    elif model.schema in ("IFC4X3", "IFC4X3_ADD2"):
        to_aas_module = experiments.instances.IFC4X3_ADD2  # pylint: disable=no-member
    elif model.schema == "IFC2X3":
        to_aas_module = experiments.instances.IFC2X3  # pylint: disable=no-member
    else:
        raise RuntimeError(f"Unhandled schema: {model.schema}")

    # Get instances for this chunk
    instances = [
        instance
        for entity in to_aas_module.ENTITIES_MAPPED_TO_SUBMODELS
        for instance in model.by_type(entity)
    ][start_idx:end_idx]

    logger = to_aas_module.Logger()

    json_counter = ByteCounter()

    # noinspection PyTypeChecker
    json_text_stream = io.TextIOWrapper(
        json_counter,
        encoding="utf-8",
        write_through=True,  # flush encoded bytes immediately
    )

    xml_counter = ByteCounter()

    # noinspection PyTypeChecker
    xml_text_stream = io.TextIOWrapper(
        xml_counter,
        encoding="utf-8",
        write_through=True,  # flush encoded bytes immediately
    )

    protobuf_counter = ByteCounter()

    submodel_json_sizes = []  # type: List[float]

    for instance in instances:
        submodel = to_aas_module.translate(instance=instance, logger=logger)
        assert isinstance(submodel, aas_types.Submodel)

        jsonable = aas_jsonization.to_jsonable(submodel)
        xml_document = aas_xmlization.to_str(submodel)
        protobuf = aas_core3_protobuf.pbization.to_pb(submodel)
        protobuf_bytes = protobuf.SerializeToString()
        assert isinstance(protobuf_bytes, bytes)

        previous_json_count = json_counter.count

        json.dump(jsonable, json_text_stream)
        xml_text_stream.write(xml_document)
        protobuf_counter.write(protobuf_bytes)

        submodel_json_size = json_counter.count - previous_json_count
        submodel_json_sizes.append(submodel_json_size)

        args.progress_counter.value += 1

    json_counter.close()
    xml_counter.close()
    protobuf_counter.close()

    return Outcome(
        submodel_count=len(instances),
        json_count=json_counter.count,
        json_gzip_count=json_counter.gzip_count,
        xml_count=xml_counter.count,
        xml_gzip_count=xml_counter.gzip_count,
        protobuf_count=protobuf_counter.count,
        protobuf_gzip_count=protobuf_counter.gzip_count,
        submodel_json_sizes=submodel_json_sizes,
    )


@dataclasses.dataclass
class Statistics:
    p0: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    p100: float
    mean: float
    std: float

    def __str__(self) -> str:
        return (
            f"min.: {self.p0:.2f}, "
            f"10%: {self.p10:.2f}, "
            f"25%: {self.p25:.2f}, "
            f"median: {self.p50:.2f}, "
            f"75%: {self.p75:.2f}, "
            f"90%: {self.p90:.2f}, "
            f"max.: {self.p100:.2f}, "
            f"mean: {self.mean:.2f} ± {self.std:.2f}"
        )


def compute_statistics(values: Sequence[float]) -> Statistics:
    length = len(values)

    # Handle empty case
    if length == 0:
        return Statistics(
            p0=math.nan,
            p10=math.nan,
            p25=math.nan,
            p50=math.nan,
            p75=math.nan,
            p90=math.nan,
            p100=math.nan,
            mean=math.nan,
            std=math.nan,
        )

    # Handle single value case
    if length == 1:
        value = values[0]
        return Statistics(
            p0=value,
            p10=value,
            p25=value,
            p50=value,
            p75=value,
            p90=value,
            p100=value,
            mean=value,
            std=0.0,
        )

    sorted_values = sorted(values)
    quantiles_4 = statistics.quantiles(sorted_values, n=4)
    quantiles_10 = statistics.quantiles(sorted_values, n=10)

    # Compute median manually from sorted values
    if length % 2 == 1:
        p50 = sorted_values[length // 2]
    else:
        p50 = (sorted_values[length // 2 - 1] + sorted_values[length // 2]) / 2.0

    return Statistics(
        p0=sorted_values[0],
        p10=quantiles_10[0],
        p25=quantiles_4[0],
        p50=p50,
        p75=quantiles_4[2],
        p90=quantiles_10[8],
        p100=sorted_values[-1],
        mean=statistics.mean(values),
        std=statistics.stdev(values),
    )


def main() -> None:
    this_dir = pathlib.Path(os.path.realpath(__file__)).parent

    model_paths = sorted((this_dir / "ifc").glob("*LF_5*.ifc"))

    table = [
        [
            "Model",
            "STEP",
            "STEP+gzip",
            "JSON",
            "JSON+gzip",
            "XML",
            "XML+gzip",
            "Protobuf",
            "Protobuf+gzip",
        ]
    ]  # type: List[List[str]]

    for model_i, model_path in enumerate(model_paths):
        underline = "=" * len(model_path.name)
        if model_i > 0:
            print()
        print(f"{model_path.name}\n{underline}\n")

        print("Loading the model...")
        model = ifcopenshell.open(str(model_path))

        to_aas_module: ModuleType
        if model.schema == "IFC4":
            to_aas_module = experiments.instances.IFC4  # pylint: disable=no-member
        elif model.schema in ("IFC4X3", "IFC4X3_ADD2"):
            to_aas_module = (
                experiments.instances.IFC4X3_ADD2
            )  # pylint: disable=no-member
        elif model.schema == "IFC2X3":
            to_aas_module = experiments.instances.IFC2X3  # pylint: disable=no-member
        else:
            raise RuntimeError(f"Unhandled schema: {model.schema}")

        logger = to_aas_module.Logger()

        print("Converting to AAS and serializing...")

        # Count total instances for chunking
        instance_count = sum(
            sum(1 for _ in model.by_type(entity))
            for entity in to_aas_module.ENTITIES_MAPPED_TO_SUBMODELS
        )

        # Create chunks for multiprocessing
        num_processes = 3
        chunks = compute_chunk_indices(instance_count, num_processes)

        with multiprocessing.Manager() as manager:
            progress_counter = manager.Value("i", 0)

            chunk_args = [
                ChunkArgs(
                    model_path=model_path,
                    chunk=chunk,
                    progress_counter=progress_counter,
                    total_instances=instance_count,
                )
                for chunk in chunks
            ]

            with tqdm.tqdm(
                total=instance_count, desc="Processing instances"
            ) as progress_bar:
                with multiprocessing.Pool(num_processes) as pool:
                    result = pool.map_async(process_chunk, chunk_args)

                    last_value = 0
                    while not result.ready():
                        current_value = progress_counter.value
                        if current_value > last_value:
                            progress_bar.update(current_value - last_value)

                            last_value = current_value

                        time.sleep(0.3)

                    # Final update
                    final_value = progress_counter.value
                    if final_value > last_value:
                        progress_bar.update(final_value - last_value)

                    outcomes = result.get()

        total_outcome = sum(outcomes, Outcome())

        entity_instance_count = sum(
            1
            for entity_name in to_aas_module.ENTITIES_MAPPED_TO_SUBMODELS
            for _ in model.by_type(entity_name)
        ) + sum(
            1
            for entity_name in (
                to_aas_module.ENTITIES_MAPPED_TO_SUBMODEL_ELEMENT_COLLECTIONS
            )
            for _ in model.by_type(entity_name)
        )

        print(
            f"There were in total {entity_instance_count} instances of IFC entities. "
            f"Out of which {total_outcome.submodel_count} were translated to submodels and "
            f"{entity_instance_count - total_outcome.submodel_count} nested "
            f"as submodel element collections."
        )

        if len(logger.messages) > 0:
            messages_joined = "\n".join(logger.messages)
            print(f"Schema violations:\n{messages_joined}")

        assert len(total_outcome.submodel_json_sizes) == total_outcome.submodel_count

        submodel_json_size_stats = compute_statistics(total_outcome.submodel_json_sizes)
        print(f"Distribution of JSON submodel size: {submodel_json_size_stats}")

        step_size = model_path.stat().st_size
        print(f"STEP serialization is: {step_size / 1024:.2f} Kb")
        step_compressed_size = len(gzip.compress(model_path.read_bytes()))
        print(f"STEP serialization + gzip is: {step_compressed_size / 1024:.2f} Kb")

        print(f"JSON serialization is: {total_outcome.json_count / 1024:.2f} Kb")
        print(
            f"JSON serialization + gzip is: {total_outcome.json_gzip_count / 1024:.2f} Kb"
        )

        print(f"XML serialization is: {total_outcome.xml_count / 1024:.2f} Kb")
        print(
            f"XML serialization + gzip is: {total_outcome.xml_gzip_count / 1024:.2f} Kb"
        )

        print(
            f"Protobuf serialization is: {total_outcome.protobuf_count / 1024:.2f} Kb"
        )
        print(
            f"Protobuf serialization + gzip is: "
            f"{total_outcome.protobuf_gzip_count / 1024:.2f} Kb"
        )

        table.append(
            [
                model_path.name,
                str(step_size),
                str(step_compressed_size),
                str(total_outcome.json_count),
                str(total_outcome.json_gzip_count),
                str(total_outcome.xml_count),
                str(total_outcome.xml_gzip_count),
                str(total_outcome.protobuf_count),
                str(total_outcome.protobuf_gzip_count),
            ]
        )

    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerows(table)

    print(f"CSV:\n{stream.getvalue()}")


if __name__ == "__main__":
    main()
