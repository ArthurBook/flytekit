import typing
from functools import partial, wraps

import mlflow
import pandas
import pandas as pd
import plotly.graph_objects as go
from mlflow import MlflowClient
from mlflow.entities.metric import Metric
from plotly.subplots import make_subplots

import flytekit
from flytekit import FlyteContextManager
from flytekit.deck import TopFrameRenderer


def metric_to_df(metrics: typing.List[Metric]) -> pd.DataFrame:
    """
    Converts mlflow Metric object to a dataframe of 2 columns ['timestamp', 'value']
    """
    t = []
    v = []
    for m in metrics:
        t.append(m.timestamp)
        v.append(m.value)
    return pd.DataFrame(list(zip(t, v)), columns=["timestamp", "value"])


def get_run_metrics(c: MlflowClient, run_id: str) -> typing.Dict[str, pandas.DataFrame]:
    """
    Extracts all metrics and returns a dictionary of metric name to the list of metric for the given run_id
    """
    r = c.get_run(run_id)
    metrics = {}
    for k in r.data.metrics.keys():
        metrics[k] = metric_to_df(metrics=c.get_metric_history(run_id=run_id, key=k))
    return metrics


def get_run_params(c: MlflowClient, run_id: str) -> typing.Optional[pd.DataFrame]:
    """
    Extracts all parameters and returns a dictionary of metric name to the list of metric for the given run_id
    """
    r = c.get_run(run_id)
    name = []
    value = []
    if r.data.params == {}:
        return None
    for k, v in r.data.params.items():
        name.append(k)
        value.append(v)
    return pd.DataFrame(list(zip(name, value)), columns=["name", "value"])


def plot_metrics(metrics: typing.Dict[str, pandas.DataFrame]) -> typing.Optional[go.Figure]:
    v = len(metrics)
    if v == 0:
        return None

    # Initialize figure with subplots
    fig = make_subplots(rows=v, cols=1, subplot_titles=list(metrics.keys()))

    # Add traces
    row = 1
    for k, v in metrics.items():
        v["timestamp"] = (v["timestamp"] - v["timestamp"][0]) / 1000
        fig.add_trace(go.Scatter(x=v["timestamp"], y=v["value"], name=k), row=row, col=1)
        row = row + 1

    fig.update_xaxes(title_text="Time (s)")
    fig.update_layout(height=700, width=900)
    return fig


def mlflow_autolog(fn=None, *, framework=mlflow.sklearn):
    """
    This decorator can be used as a nested decorator for a ``@task`` and it will automatically enable mlflow autologging,
    for the given ``framework``. If framework is not provided then the autologging is enabled for ``sklearn``
    .. code-block::python
        @task
        @mlflow_autolog(framework=mlflow.tensorflow)
        def my_tensorflow_trainer():
            ...
    One benefit of doing so is that the mlflow metrics are then rendered inline using FlyteDecks and can be viewed
    in jupyter notebook, as well as in hosted Flyte environment
    .. code-block:: python
        with flytekit.new_context() as ctx:
            my_tensorflow_trainer()
            ctx.get_deck()  # IPython.display
    The decorator starts a new run, with mlflow for the task
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        framework.autolog()
        ctx = FlyteContextManager.current_context()
        task_id = ctx.user_space_params.task_id
        mlflow.set_experiment(fn.__name__)
        with mlflow.start_run():
            # Get execution id and flyte console link from propeller.
            mlflow.log_param("Flyte Console", "http://flyte:30081/console/projects/flytesnacks/domains/development/executions/a4xlbh7wxtc2skdt2vjc?duration=all")
            out = fn(*args, **kwargs)
            run = mlflow.active_run()
            if run is not None:
                client = MlflowClient()
                run_id = run.info.run_id
                metrics = get_run_metrics(client, run_id)
                figure = plot_metrics(metrics)
                if figure:
                    flytekit.Deck("mlflow metrics", figure.to_html())
                params = get_run_params(client, run_id)
                if params is not None:
                    flytekit.Deck("mlflow params", TopFrameRenderer().to_html(params))
        return out

    if fn is None:
        return partial(mlflow_autolog, framework=framework)

    return wrapper
