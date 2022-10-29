import os
from typing import Type

import tensorflow as tf

from flytekit.core.context_manager import FlyteContext
from flytekit.core.type_engine import TypeEngine, TypeTransformer, TypeTransformerFailedError
from flytekit.models.core import types as _core_types
from flytekit.models.literals import Blob, BlobMetadata, Literal, LiteralCollection, Primitive, Scalar
from flytekit.models.types import LiteralType


class TensorFlowTensorTransformer(TypeTransformer[tf.Tensor]):
    """
    TypeTransformer that supports tf.tensor as a native type
    """

    TENSORFLOW_FORMAT = "TensorflowTensor"

    def __init__(self):
        super().__init__(name="Tensorflow Tensor", t=tf.Tensor)

    def get_literal_type(self, t: Type[tf.Tensor]) -> LiteralType:
        return LiteralType(
            blob=_core_types.BlobType(
                format=self.TENSORFLOW_FORMAT,
                dimensionality=_core_types.BlobType.BlobDimensionality.SINGLE,
            )
        )

    def to_literal(
        self,
        ctx: FlyteContext,
        python_val: tf.Tensor,
        python_type: Type[tf.Tensor],
        expected: LiteralType,
    ) -> Literal:
        meta = BlobMetadata(
            type=_core_types.BlobType(
                format=self.TENSORFLOW_FORMAT,
                dimensionality=_core_types.BlobType.BlobDimensionality.SINGLE,
            )
        )

        local_path = ctx.file_access.get_random_local_path()

        # Save the `tf.tensor` as a file on disk
        local_path = os.path.join(local_path, "tensor_data")
        tf.io.write_file(local_path, tf.io.serialize_tensor(python_val))

        tensor_dtype = python_val.dtype.name

        remote_path = ctx.file_access.get_random_remote_path(local_path)
        ctx.file_access.put_data(local_path, remote_path, is_multipart=False)
        return Literal(
            collection=LiteralCollection(
                literals=[
                    Literal(scalar=Scalar(blob=Blob(metadata=meta, uri=remote_path))),
                    Literal(scalar=Scalar(primitive=Primitive(string_value=tensor_dtype))),
                ]
            )
        )

    def to_python_value(
        self, ctx: FlyteContext, lv: Literal, expected_python_type: Type[tf.Tensor]
    ) -> tf.Tensor:  # Set 'expected_python_type' as an optional argument
        try:
            uri = lv.collection.literals[0].scalar.blob.uri
        except AttributeError:
            TypeTransformerFailedError(f"Cannot convert from {lv} to {expected_python_type}")

        local_path = ctx.file_access.get_random_local_path()
        ctx.file_access.get_data(uri, local_path, is_multipart=False)
        tensor_dtype = tf.dtypes.as_dtype(lv.collection.literals[1].scalar.primitive.string_value)

        read_serial = tf.io.read_file(local_path)

        return tf.io.parse_tensor(read_serial, out_type=tensor_dtype)

    def guess_python_type(self, literal_type: LiteralType) -> Type[tf.Tensor]:
        if (
            literal_type.blob is not None
            and literal_type.blob.dimensionality == _core_types.BlobType.BlobDimensionality.SINGLE
            and literal_type.blob.format == self.TENSORFLOW_FORMAT
        ):
            return tf.Tensor

        raise ValueError(f"Transformer {self} cannot reverse {literal_type}")


TypeEngine.register(TensorFlowTensorTransformer())