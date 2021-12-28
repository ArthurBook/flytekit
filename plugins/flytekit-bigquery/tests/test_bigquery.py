from collections import OrderedDict

import pytest
from flytekitplugins.bigquery import BigQueryConfig, BigQueryTask
from google.cloud.bigquery import QueryJobConfig
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Struct

from flytekit import kwtypes, workflow
from flytekit.extend import Image, ImageConfig, SerializationSettings, get_serializable
from flytekit.types.schema import FlyteSchema

query_template = """
            insert overwrite directory '{{ .rawOutputDataPrefix }}' stored as parquet
            select *
            from my_table
            where ds = '{{ .Inputs.ds }}'
        """


def test_serialization():
    bigquery_task = BigQueryTask(
        name="flytekit.demo.bigquery_task.query",
        inputs=kwtypes(ds=str),
        task_config=BigQueryConfig(
            ProjectID="Flyte", Location="Asia", QueryJobConfig=QueryJobConfig(allow_large_results=True)
        ),
        query_template=query_template,
        output_schema_type=FlyteSchema,
    )

    @workflow
    def my_wf(ds: str) -> FlyteSchema:
        return bigquery_task(ds=ds)

    default_img = Image(name="default", fqn="test", tag="tag")
    serialization_settings = SerializationSettings(
        project="proj",
        domain="dom",
        version="123",
        image_config=ImageConfig(default_image=default_img, images=[default_img]),
        env={},
    )

    task_spec = get_serializable(OrderedDict(), serialization_settings, bigquery_task)

    assert "{{ .rawOutputDataPrefix" in task_spec.template.sql.statement
    assert "insert overwrite directory" in task_spec.template.sql.statement
    assert task_spec.template.sql.dialect == task_spec.template.sql.Dialect.ANSI
    s = Struct()
    s.update({"ProjectID": "Flyte", "Location": "Asia", "allowLargeResults": True})
    assert task_spec.template.custom == json_format.MessageToDict(s)
    assert len(task_spec.template.interface.inputs) == 1
    assert len(task_spec.template.interface.outputs) == 1

    admin_workflow_spec = get_serializable(OrderedDict(), serialization_settings, my_wf)
    assert admin_workflow_spec.template.interface.outputs["o0"].type.schema is not None
    assert admin_workflow_spec.template.outputs[0].var == "o0"
    assert admin_workflow_spec.template.outputs[0].binding.promise.node_id == "n0"
    assert admin_workflow_spec.template.outputs[0].binding.promise.var == "results"


def test_local_exec():
    bigquery_task = BigQueryTask(
        name="flytekit.demo.bigquery_task.query2",
        inputs=kwtypes(ds=str),
        query_template=query_template,
        task_config=BigQueryConfig(ProjectID="Flyte", Location="Asia"),
        output_schema_type=FlyteSchema,
    )

    assert len(bigquery_task.interface.inputs) == 1
    assert len(bigquery_task.interface.outputs) == 1

    # will not run locally
    with pytest.raises(Exception):
        bigquery_task()
