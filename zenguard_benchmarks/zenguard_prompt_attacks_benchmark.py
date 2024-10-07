import json
from typing import Optional, Union

import httpx
import requests
import matplotlib.pyplot as plt
import pandas as pd
from datasets import load_dataset
from tqdm import tqdm

CONFIG_TIMEOUT = 60
CONFIG_TIME_BETWEEN_REQUESTS = 0.1
BACKEND = "https://api.zenguard.ai"
PROMPT_ATTACKS_API = f"{BACKEND}/v1/detect/prompt_injection"
ZEN_BENCHMARK_API = f"{BACKEND}/v1/benchmark/zen"


class ZenPromptAttacksBenchmark:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def init_dataset(
        self, dataset_name: str, prompt_column: str, label_column: Optional[str] = None
    ) -> None:
        self._dataset_name = dataset_name
        self._prompt_column = prompt_column
        self._label_column = label_column
        self._results: dict = {}
        try:
            self._dataset = load_dataset(dataset_name)
            if "train" not in self._dataset:
                raise ValueError("Dataset must contain at least one 'train' split")
        except Exception as e:
            raise ValueError(f"Failed to load dataset: {e}")

    def detect_prompt_injection(self, prompt: str) -> bool:
        try:
            response = httpx.post(
                PROMPT_ATTACKS_API,
                headers={"x-api-key": self._api_key},
                json={"messages": [prompt]},
                timeout=CONFIG_TIMEOUT,
            )
            response.raise_for_status()
        except httpx.RequestError as e:
            raise RuntimeError(
                f"An error occurred while making the request: {str(e)}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Received an unexpected status code: {response.status_code}\nResponse content: {response.json()}"
            ) from e

        return response.json().get("is_detected")

    def _normalize_label(self, label: Union[str, int, None]) -> bool:
        # True means the prompt is a prompt attack
        # False means the prompt is not a prompt attack
        if label is None:
            return True

        if isinstance(label, int):
            return label == 1

        if isinstance(label, str):
            if label.lower() == "malicious":
                return True
            if label.lower() == "true":
                return True

        return False

    def benchmark(self):
        with requests.post(ZEN_BENCHMARK_API, stream=True) as response:
            total_prompts = None
            with tqdm(total=100, unit='%', desc="Zenguard Benchmark") as progress_bar:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        data = json.loads(chunk.decode())

                        if total_prompts is None:
                            total_prompts = data['total_number_of_prompts']
                            progress_bar.total = total_prompts
                            progress_bar.unit = 'prompts'

                        progress_bar.n = data['number_of_prompts_completed']
                        progress_bar.refresh()

            # Print results below the progress bar
            print(f"\nScore: {data['score']}")
            print("\nCategories:")
            for category in data['categories']:
                category_score = int(category['correct_number']) / int(category['total'])
                print(f"\t{category['category_name']} Total: {category['total']}, Correct: {category['correct_number']}, Score: {category_score}")
                
    def plot(self, results: Optional[dict] = None) -> None:
        if results is None:
            results = self._results

        if not results:
            raise ValueError("No results to plot")

        data = {
            "Result": ["Total", "Correct", "False Positive", "False Negative"],
            "Count": [
                results["total_samples"],
                results["correct"],
                results["false_positive"],
                results["false_negative"],
            ],
        }

        df = pd.DataFrame(data)
        plt.figure(figsize=(8, 6))

        plt.bar(df["Result"], df["Count"], color=["blue", "green", "orange", "red"])
        plt.title(f"ZenGuard AI Benchmark Results against {self._dataset_name}")
        plt.xlabel("Result Type")
        plt.ylabel("Count")
        plt.show()
