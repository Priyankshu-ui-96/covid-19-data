import tempfile
from datetime import datetime
import re
import locale

import requests
import pandas as pd
import PyPDF2

from vax.utils.incremental import merge_with_current_data, clean_count
from vax.utils.utils import get_soup


class Gambia:

    def __init__(self, source_url: str, location: str):
        self.source_url = source_url
        self.location = location
        self._num_links_max = 6

    def read(self, last_update) -> pd.Series:
        links = self.get_pdf_links(self.source_url)
        data = []
        for link in links[:self._num_links_max]:
            _data = self.parse_data_pdf(link)
            if _data["date"] <= last_update:
                break
            data.append(_data)
        df = pd.DataFrame(data)
        return df

    def get_pdf_links(self, source) -> list:
        soup = get_soup(source, verify=False)
        links = soup.find_all(class_="wp-block-file")
        return [link.a.get("href") for link in links]

    def parse_data_pdf(self, link) -> dict:
        text = self._get_pdf_text(link)
        regex = (
            r"([\d,]+) people have been vaccinated against COVID-19 as of (\d{1,2})(?:th|nd|st|rd) ([a-zA-Z]+) (202\d)"
        )
        match = re.search(regex, text)
        people_vaccinated = clean_count(match.group(1))
        date_raw = " ".join(match.group(2, 3, 4))
        date_str = datetime.strptime(date_raw, "%d %B %Y").strftime("%Y-%m-%d")
        return {
            "total_vaccinations": people_vaccinated,
            "people_vaccinated": people_vaccinated,
            "people_fully_vaccinated": 0,
            "date": date_str,
            "source_url": link,
        }

    def _get_pdf_text(self, url) -> str:
        with tempfile.NamedTemporaryFile() as tf:
            with open(tf.name, mode="wb") as f:
                f.write(requests.get(url, verify=False).content)
            with open(tf.name, mode="rb") as f:
                reader = PyPDF2.PdfFileReader(f)
                page = reader.getPage(0)
                text = page.extractText()
        text = text.replace("\n", "")
        return text

    def pipe_drop_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        return (
            df.sort_values("date")
            .drop_duplicates(
                subset=["total_vaccinations", "people_vaccinated", "people_fully_vaccinated"],
                keep="first"
            )
        )

    def pipe_location(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.assign(location=self.location)

    def pipe_vaccine(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.assign(vaccine="Oxford/AstraZeneca")

    def pipe_select_output_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        return df[[
            "location",
            "date",
            "vaccine",
            "source_url",
            "total_vaccinations",
            "people_vaccinated",
            "people_fully_vaccinated"
        ]]

    def pipeline(self, df: pd.Series) -> pd.Series:
        return (
            df
            .pipe(self.pipe_drop_duplicates)
            .pipe(self.pipe_location)
            .pipe(self.pipe_vaccine)
            .pipe(self.pipe_select_output_columns)
        )

    def to_csv(self, paths):
        """Generalized."""
        output_file = paths.tmp_vax_out(self.location)
        last_update = pd.read_csv(output_file).date.max()
        df = self.read(last_update)
        if df is not None:
            df = df.pipe(self.pipeline)
            df = merge_with_current_data(df, output_file)
            df = df.pipe(self.pipe_drop_duplicates)
            df.to_csv(output_file, index=False)


def main(paths):
    locale.setlocale(locale.LC_TIME, "en_GB")
    Gambia(
        source_url="https://www.moh.gov.gm/covid-19-report",
        location="Gambia",
    ).to_csv(paths) 


if __name__ == "__main__":
    main()
