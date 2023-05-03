"""Async workflows prototype."""

import asyncio
from typing import NamedTuple

import pandas as pd
from sklearn.datasets import load_wine
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

from flytekit import workflow, task, Secret
from flytekit.configuration import Config, PlatformConfig
from flytekit.experimental import eager
from flytekit.remote import FlyteRemote

CACHE_VERSION = "4"

class CustomException(Exception): ...

BestModel = NamedTuple("BestModel", model=LogisticRegression, metric=float)


@task(cache=True, cache_version=CACHE_VERSION)
def get_data() -> pd.DataFrame:
    """Get the wine dataset."""
    return load_wine(as_frame=True).frame


@task(cache=True, cache_version=CACHE_VERSION)
def process_data(data: pd.DataFrame) -> pd.DataFrame:
    """Simplify the task from a 3-class to a binary classification problem."""
    return data.assign(target=lambda x: x["target"].where(x["target"] == 0, 1))


@task(cache=True, cache_version=CACHE_VERSION)
def train_model(data: pd.DataFrame, hyperparameters: dict) -> LogisticRegression:
    """Train a model on the wine dataset."""
    features = data.drop("target", axis="columns")
    target = data["target"]
    return LogisticRegression(max_iter=3000, **hyperparameters).fit(features, target)


@task
def evaluate_model(data: pd.DataFrame, model: LogisticRegression) -> float:
    """Train a model on the wine dataset."""
    features = data.drop("target", axis="columns")
    target = data["target"]
    return float(accuracy_score(target, model.predict(features)))


Config.for_sandbox
remote = FlyteRemote(
    # config=Config.for_sandbox(),
    config=Config(
        platform=PlatformConfig(
            endpoint="development.uniondemo.run",
            auth_mode="Pkce",
            client_id="flytepropeller",
            insecure=False,
        ),
    ),
    default_project="flytesnacks",
    default_domain="development",
)

@eager(
    remote=remote,
    secret_requests=[Secret(group="eager-mode", key="client_secret")],
    disable_deck=False,
)
async def main() -> BestModel:
    data = await get_data()
    processed_data = await process_data(data=data)

    # split the data
    try:
        train, test = train_test_split(processed_data, test_size=0.2)
    except Exception as exc:
        raise CustomException(str(exc)) from exc

    models = await asyncio.gather(*[
        train_model(data=train, hyperparameters={"C": x})
        for x in [0.1, 0.01, 0.001, 0.0001, 0.00001]
    ])
    results = await asyncio.gather(*[
        evaluate_model(data=test, model=model) for model in models
    ])

    best_model, best_result = None, float("-inf")
    for model, result in zip(models, results):
        if result > best_result:
            best_model, best_result = model, result

    assert best_model is not None, "model cannot be None!"
    return best_model, best_result


@workflow
def wf() -> BestModel:
    return main()


if __name__ == "__main__":
    print("training model")
    model = asyncio.run(main())
    print(f"trained model: {model}")