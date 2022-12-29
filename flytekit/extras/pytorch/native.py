import pathlib
from typing import Generic, Type, TypeVar

import torch
from flyteidl.core import types_pb2
from flyteidl.core.literals_pb2 import Blob, BlobMetadata, Literal, Scalar
from flyteidl.core.types_pb2 import LiteralType

from flytekit.core.context_manager import FlyteContext
from flytekit.core.type_engine import TypeEngine, TypeTransformer, TypeTransformerFailedError

T = TypeVar("T")


class PyTorchTypeTransformer(TypeTransformer, Generic[T]):
    def get_literal_type(self, t: Type[T]) -> LiteralType:
        return LiteralType(
            blob=types_pb2.BlobType(
                format=self.PYTORCH_FORMAT,
                dimensionality=types_pb2.BlobType.SINGLE,
            )
        )

    def to_literal(
        self,
        ctx: FlyteContext,
        python_val: T,
        python_type: Type[T],
        expected: LiteralType,
    ) -> Literal:
        meta = BlobMetadata(
            type=types_pb2.BlobType(
                format=self.PYTORCH_FORMAT,
                dimensionality=types_pb2.BlobType.SINGLE,
            )
        )

        local_path = ctx.file_access.get_random_local_path() + ".pt"
        pathlib.Path(local_path).parent.mkdir(parents=True, exist_ok=True)

        # save pytorch tensor/module to a file
        torch.save(python_val, local_path)

        remote_path = ctx.file_access.get_random_remote_path(local_path)
        ctx.file_access.put_data(local_path, remote_path, is_multipart=False)
        return Literal(scalar=Scalar(blob=Blob(metadata=meta, uri=remote_path)))

    def to_python_value(self, ctx: FlyteContext, lv: Literal, expected_python_type: Type[T]) -> T:
        try:
            uri = lv.scalar.blob.uri
        except AttributeError:
            TypeTransformerFailedError(f"Cannot convert from {lv} to {expected_python_type}")

        local_path = ctx.file_access.get_random_local_path()
        ctx.file_access.get_data(uri, local_path, is_multipart=False)

        # cpu <-> gpu conversion
        if torch.cuda.is_available():
            map_location = "cuda:0"
        else:
            map_location = torch.device("cpu")

        # load pytorch tensor/module from a file
        return torch.load(local_path, map_location=map_location)

    def guess_python_type(self, literal_type: LiteralType) -> Type[T]:
        if (
            literal_type.blob is not None
            and literal_type.blob.dimensionality == types_pb2.BlobType.SINGLE
            and literal_type.blob.format == self.PYTORCH_FORMAT
        ):
            return T

        raise ValueError(f"Transformer {self} cannot reverse {literal_type}")


class PyTorchTensorTransformer(PyTorchTypeTransformer[torch.Tensor]):
    PYTORCH_FORMAT = "PyTorchTensor"

    def __init__(self):
        super().__init__(name="PyTorch Tensor", t=torch.Tensor)


class PyTorchModuleTransformer(PyTorchTypeTransformer[torch.nn.Module]):
    PYTORCH_FORMAT = "PyTorchModule"

    def __init__(self):
        super().__init__(name="PyTorch Module", t=torch.nn.Module)


TypeEngine.register(PyTorchTensorTransformer())
TypeEngine.register(PyTorchModuleTransformer())
