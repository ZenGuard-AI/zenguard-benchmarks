import time
from typing import Optional

import httpx
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
        try:
            self._dataset = load_dataset(dataset_name)["train"]
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
        total_samples = len(self._dataset)
        correct = 0
        false_positive = 0  # ZenGuard detected a prompt attack, but the label was not a prompt attack
        false_negative = 0  # ZenGuard did not detect a prompt attack, but the label was a prompt attack

        for sample in tqdm(self._dataset, total=total_samples, desc="Benchmarking"):
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
        print(f"Total samples: {total_samples}")
        print(f"Correct: {correct}")
        print(f"False positive: {false_positive}")
        print(f"False negative: {false_negative}")

        return {
            "total_samples": total_samples,
            "correct": correct,
            "false_positive": false_positive,
            "false_negative": false_negative,
        }


if __name__ == "__main__":
    api_key = "jzVHclxS5Qv4ggHOukA5hSZTU0ZGEVxs3xjkilQP7bY"
    benchmark = ZenPromptAttacksBenchmark(api_key)
    benchmark.init_dataset("JasperLS/prompt-injections", "text", "label")
    benchmark.benchmark()
