import time
from typing import Optional

import httpx
import matplotlib.pyplot as plt
import pandas as pd
from datasets import load_dataset
from tqdm import tqdm

CONFIG_TIMEOUT = 60
CONFIG_TIME_BETWEEN_REQUESTS = 0.1
PROMPT_ATTACKS_API = "https://api.zenguard.ai/v1/detect/prompt_injection"


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

    def _normalize_label(self, label: str | int | None) -> bool:
        # True means the prompt is a prompt attack
        # False means the prompt is not a prompt attack
        if label is None:
            return True
        if isinstance(label, int):
            return label == 1

        return label.lower() == "true"

    def benchmark(self) -> dict:
        total_samples = len(self._dataset["train"]) + len(self._dataset["test"])
        correct = 0
        false_positive = 0  # ZenGuard detected a prompt attack, but the label was not a prompt attack
        false_negative = 0  # ZenGuard did not detect a prompt attack, but the label was a prompt attack

        for split in ["train", "test"]:
            if split in self._dataset:
                for sample in tqdm(
                    self._dataset[split],
                    total=len(self._dataset[split]),
                    desc=f"Benchmarking progress for: {split}",
                ):
                    prompt = sample[self._prompt_column]
                    label = sample[self._label_column]
                    zenguard_is_detected = self.detect_prompt_injection(prompt)
                    real_is_detected = self._normalize_label(label)
                    if zenguard_is_detected and real_is_detected:
                        correct += 1
                    elif not zenguard_is_detected and not real_is_detected:
                        correct += 1
                    elif zenguard_is_detected and not real_is_detected:
                        false_positive += 1
                    elif not zenguard_is_detected and real_is_detected:
                        false_negative += 1
                    time.sleep(CONFIG_TIME_BETWEEN_REQUESTS)

        print("Dataset:", self._dataset_name)
        print("ZenGuard Benchmark Results:")
        print(f"Total Samples: {total_samples}")
        print(f"    Correct: {correct}")
        print(f"    False Positives: {false_positive}")
        print(f"    False Negatives: {false_negative}")
        print(f"    Accuracy: {correct / total_samples:.2%}")
        print("======== RUN FINISHED ========")

        self._results = {
            "total_samples": total_samples,
            "correct": correct,
            "false_positive": false_positive,
            "false_negative": false_negative,
        }
        return self._results

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
