"""TF-IDF + logistic regression Stage 1 baseline (CPU; a few minutes on either machine).

The utterance-only model is the artifact probe: if it already separates direct
from indirect paraphrases well, surface wording carries most of the signal.
With ``use_context``, utterance and context get separate vocabularies, so the
model can weight them independently.

    python -m src.stage1.tfidf --config configs/stage1/tfidf_utterance.toml --seed 13
    python -m src.stage1.tfidf --config configs/stage1/tfidf_context.toml --seed 13 --train-condition one
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Sequence

from src.stage1 import runner
from src.stage1.data import STAGE1_LABELS

logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    runner.add_common_args(parser)
    args = parser.parse_args(argv)
    runner.configure_logging()
    started = time.time()
    try:
        config = runner.load(args, {})
        if config.kind != "tfidf" or config.tfidf is None:
            raise ValueError("this trainer needs kind = 'tfidf' and a [tfidf] table")
        settings = config.tfidf
        prepared = runner.prepare(config, args.smoke)

        from scipy.sparse import hstack
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression

        def vectorizer() -> TfidfVectorizer:
            return TfidfVectorizer(ngram_range=(1, settings.ngram_max), min_df=settings.min_df,
                                   sublinear_tf=True)

        utterance_vectorizer = vectorizer()
        context_vectorizer = vectorizer() if settings.use_context else None

        def features(pairs: Sequence[runner.Pair], fit: bool = False):
            utterances = [utterance for _, utterance in pairs]
            matrix = (utterance_vectorizer.fit_transform if fit else utterance_vectorizer.transform)(utterances)
            if context_vectorizer is None:
                return matrix
            contexts = [context for context, _ in pairs]
            context_matrix = (context_vectorizer.fit_transform if fit else context_vectorizer.transform)(contexts)
            return hstack([matrix, context_matrix]).tocsr()

        train_features = features(prepared.train_inputs, fit=True)
        classifier = LogisticRegression(C=settings.c, max_iter=settings.max_iter, random_state=args.seed)
        classifier.fit(train_features, [STAGE1_LABELS.index(e.label) for e in prepared.train])
        logger.info("fit on %d examples x %d features", *train_features.shape)

        predictions = []
        for condition, pairs in prepared.eval_inputs.items():
            probabilities = classifier.predict_proba(features(pairs))  # columns: classes 0, 1, 2
            predictions += runner.prediction_rows(prepared.eval, condition, probabilities)
        model_info = {"name": "tfidf_logreg", "use_context": settings.use_context,
                      "n_features": train_features.shape[1], "iterations": int(max(classifier.n_iter_))}
        runner.finish(args, config, prepared, predictions, model_info, started)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        logger.error("TF-IDF run failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
