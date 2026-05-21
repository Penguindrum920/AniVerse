"""Train the local anime retrieval model."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from embeddings.local_retrieval_model import DEFAULT_MODEL_PATH, train_and_save_model


def main():
    parser = argparse.ArgumentParser(description="Train AniVerse local anime retrieval model")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_MODEL_PATH,
        help="Output joblib artifact path",
    )
    args = parser.parse_args()

    model = train_and_save_model(model_path=args.output)
    print(f"Trained retrieval model with {model.get_count()} anime")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
