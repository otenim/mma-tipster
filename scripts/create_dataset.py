import pandas as pd
import click
import json
import numpy as np
from scraper.spiders.constants import *
from scraper.spiders.fighters_spider import infer, calc_minutes, calc_rounds
from typing import Union


@click.command()
@click.argument(
    "jsonfile", type=click.Path(exists=True, dir_okay=False, resolve_path=True)
)
def main(jsonfile: str):
    # Load json file
    jsondata = None
    with open(jsonfile) as fp:
        jsondata = json.load(fp)

    # Load dataframe of fighter data
    df_fighters = pd.json_normalize(jsondata).drop(["results"], axis="columns")
    df_fighters.info(verbose=True, show_counts=True)

    # Load dataframe of result data
    df_results = pd.json_normalize(jsondata, record_path="results", meta=["id"])
    df_results.info(verbose=True, show_counts=True)

    # Merge fighters & results
    df = (
        pd.merge(df_fighters, df_results, on="id")
        .drop(
            [
                "url",
                "name",
                "nickname",
                "born",
                "out_of",
                "affiliation.url",
                "affiliation.name",
                "promotion.url",
                "opponent.name",
                "opponent.url",
                "foundation_styles",
                "odds",
                "title_info.as",
                "title_info.for",
            ],
            axis="columns",
        )
        .astype(
            {
                "id": "string",
                "nationality": "string",
                "weight_class": "string",
                "career_earnings": "float32",
                "height": "float32",
                "reach": "float32",
                "affiliation.id": "string",
                "head_coach": "string",
                "college": "string",
                "division": "string",
                "sport": "string",
                "status": "string",
                "age": "float32",
                "billing": "string",
                "referee": "string",
                "promotion.id": "string",
                "ended_by.type": "string",
                "ended_by.detail": "string",
                "ended_at.round": "float32",
                "ended_at.time.m": "float32",
                "ended_at.time.s": "float32",
                "ended_at.elapsed.m": "float32",
                "ended_at.elapsed.s": "float32",
                "regulation.format": "string",
                "regulation.minutes": "float32",
                "regulation.rounds": "float32",
                "weight.class": "string",
                "weight.limit": "float32",
                "weight.weigh_in": "float32",
                "opponent.id": "string",
            }
        )
    )
    df["date_of_birth"] = pd.to_datetime(df["date_of_birth"], format="%Y-%m-%d")
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")

    # Fill height & reach
    df = fill_height(df)
    df = fill_reach(df)

    # Fill nans with "n/a"
    for c in [
        "nationality",
        "head_coach",
        "college",
        "affiliation.id",
        "referee",
        "billing",
        "promotion.id",
    ]:
        df[c].fillna("n/a", inplace=True)

    # Fill date_of_birth
    df = fill_date_of_birth(df)

    # Fill age
    df["age"].fillna(
        ((df["date"] - df["date_of_birth"]).dt.days / 365.25).astype("float32"),
        inplace=True,
    )

    # Fill weight_class

    # Fill ended_by
    df = fill_ended_by(df)

    # Fill regulation
    df = fill_regulation(df)

    # Imputate column "duration"
    # df["duration.str"] = (
    #     df["duration"]
    #     .apply(lambda x: x if x is np.nan else "-".join(list(map(lambda n: str(n), x))))
    #     .astype("string")
    # )
    # df["duration.str"] = df.groupby(["sport", "division"])["duration.str"].transform(
    #     lambda x: x if x.mode().empty else x.fillna(x.mode().iat[0])
    # )
    # if count_nan(df["duration.str"]) > 0:
    #     df["duration.str"] = df.groupby("sport")["duration.str"].transform(
    #         lambda x: x if x.mode().empty else x.fillna(x.mode().iat[0])
    #     )
    # if count_nan(df["duration.str"]) > 0:
    #     df["duration.str"].fillna(df["duration.str"].mode().iat[0], inplace=True)
    # df["duration"].fillna(
    #     df["duration.str"].apply(
    #         lambda x: x
    #         if x is np.nan
    #         else [-1]
    #         if x == "-1"
    #         else list(map(lambda s: int(s), x.split("-")))
    #     ),
    #     inplace=True,
    # )
    # df = df.drop(["duration.str"], axis="columns")
    # df["duration.total"] = (
    #     df["duration"].apply(lambda x: x if x is np.nan else sum(x)).astype("float32")
    # )
    # df["ended_at.elapsed"] = df["ended_at.time.m"] + df["ended_at.time.s"] / 60.0
    df.info(show_counts=True, verbose=True)


def count_nan(x: Union[pd.Series, pd.DataFrame]) -> int:
    if isinstance(x, pd.Series):
        return x.isnull().sum()
    return x.isnull().sum().sum()


def fill_height(df: pd.DataFrame) -> pd.DataFrame:
    df["height"] = df.groupby(["weight_class", "nationality"])["height"].transform(
        lambda x: x.fillna(x.mean())
    )
    if count_nan(df["height"]) > 0:
        df["height"] = df.groupby("weight_class")["height"].transform(
            lambda x: x.fillna(x.mean())
        )
    if count_nan(df["height"]) > 0:
        df["height"] = df["height"].fillna(df["height"].mean())
    return df


def fill_reach(df: pd.DataFrame) -> pd.DataFrame:
    df["reach"] = df.groupby(["weight_class", "nationality"])["reach"].transform(
        lambda x: x.fillna(x.mean())
    )
    if count_nan(df["reach"]) > 0:
        df["reach"] = df.groupby("weight_class")["reach"].transform(
            lambda x: x.fillna(x.mean())
        )
    if count_nan(df["reach"]) > 0:
        df["reach"].fillna(df["reach"].mean(), inplace=True)
    return df


def fill_date_of_birth(df: pd.DataFrame) -> pd.DataFrame:
    date_at_debut = df.groupby("id")["date"].min()
    mean_age_at_debut = df.groupby("id")["age"].min().mean()
    date_of_birth_inferred = (
        date_at_debut - pd.Timedelta(mean_age_at_debut * 365.25, unit="d")
    ).rename("date_of_birth.inferred")
    merged = pd.merge(
        df, date_of_birth_inferred, left_on="id", right_index=True, how="left"
    )
    df["date_of_birth"].fillna(merged["date_of_birth.inferred"], inplace=True)
    return df


def fill_ended_by(df: pd.DataFrame) -> pd.DataFrame:
    df["ended_by.detail"] = df.groupby("id")["ended_by.detail"].transform(
        lambda x: x if x.mode().empty else x.fillna(x.mode().iat[0])
    )
    if count_nan(df["ended_by.detail"]) > 0:
        df["ended_by.detail"] = df.groupby("weight_class")["ended_by.detail"].transform(
            lambda x: x if x.mode().empty else x.fillna(x.mode().iat[0])
        )
    if count_nan(df["ended_by.detail"]) > 0:
        df["ended_by.detail"].fillna(df["ended_by.detail"].mode().iat[0])
    df["ended_by.type"].fillna(
        (df["ended_by.detail"].apply(lambda x: infer(x))).astype("string"), inplace=True
    )
    return df


def fill_regulation(df: pd.DataFrame) -> pd.DataFrame:
    # Fill format
    df["regulation.format"] = df.groupby(["sport", "division"])[
        "regulation.format"
    ].transform(lambda x: x if x.mode().empty else x.fillna(x.mode().iat[0]))
    if count_nan(df["regulation.format"]) > 0:
        df["regulation.format"] = df.groupby("sport")["regulation.format"].transform(
            lambda x: x if x.mode().empty else x.fillna(x.mode().iat[0])
        )
    if count_nan(df["regulation.format"]) > 0:
        df["regulation.format"].fillna(
            df["regulation.format"].mode().iat[0], inplace=True
        )

    # Fill rounds
    df["regulation.rounds"].fillna(
        df["regulation.format"]
        .apply(lambda x: x if x is np.nan else 1.0 if x == "*" else calc_rounds(x))
        .astype(df["regulation.rounds"].dtype),
        inplace=True,
    )
    if count_nan(df["regulation.rounds"]) > 0:
        df["regulation.rounds"].fillna(df["ended_at.round"], inplace=True)

    # Fill minutes
    df["regulation.minutes"].fillna(
        df["regulation.format"]
        .apply(lambda x: x if x is np.nan else np.nan if "*" in x else calc_minutes(x))
        .astype(df["regulation.minutes"].dtype),
        inplace=True,
    )
    if count_nan(df["regulation.minutes"]) > 0:
        df["regulation.minutes"].fillna(
            df["ended_at.elapsed.m"] + df["ended_at.elapsed.s"] / 60, inplace=True
        )
    if count_nan(df["regulation.minutes"]) > 0:
        mask = df["regulation.format"] == "*"
        masked = df["regulation.minutes"][mask]
        df["regulation.minutes"][mask] = masked.fillna(masked.mean())
    return df


if __name__ == "__main__":
    main()
