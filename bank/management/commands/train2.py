import json
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import joblib

# --------------------------------------------------
# 1. Cleaning Function (AS REQUESTED)
# --------------------------------------------------
def clean_text(text):
    text = text.upper()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def top_k_accuracy(y_true, y_proba, classes, k=3):
    correct = 0

    for i in range(len(y_true)):
        top_k_indices = np.argsort(y_proba[i])[-k:]
        top_k_labels = [classes[j] for j in top_k_indices]

        if y_true[i] in top_k_labels:
            correct += 1

    return correct / len(y_true)

# --------------------------------------------------
# 2. Training + Evaluation
# --------------------------------------------------
def train_tfidf_logistic(data, print_samples=20):
    """
    data: list of (description, party_code)
    print_samples: how many test rows to print
    """

    descriptions = [clean_text(d) for d, _ in data]
    labels = [y for _, y in data]
    from collections import Counter
    label_counts = Counter(labels)
    MIN_SAMPLES = 2
    labels = [
            y if label_counts[y] >= MIN_SAMPLES else "OTHER"
        for y in labels
    ]

    X_train, X_test, y_train, y_test = train_test_split(
        descriptions,
        labels,
        test_size=0.2,
        random_state=42,
        stratify=labels
    )

    # TF-IDF (char n-grams)
    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=(3, 6),
        min_df=2,
        max_df=0.95,
        sublinear_tf=True
    )

    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)

    # Logistic Regression
    model = LogisticRegression(
        max_iter=1000,
        n_jobs=-1,
        class_weight="balanced"
    )

    model.fit(X_train_vec, y_train)

    # Evaluation
    y_pred = model.predict(X_test_vec)
    y_proba = model.predict_proba(X_test_vec)


    print("\n================ MODEL EVALUATION ================\n")
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}\n")
    print(classification_report(y_test, y_pred))

    # --------------------------------------------------
    # 3. Print Test Predictions vs Actual
    # --------------------------------------------------
    print("\n================ SAMPLE TEST PREDICTIONS ================\n")

    classes = model.classes_

    for i in range(min(print_samples, len(X_test))):
        desc = X_test[i]
        actual = y_test[i]
        predicted = y_pred[i]

        probs = y_proba[i]
        ranked = sorted(
            zip(classes, probs),
            key=lambda x: x[1],
            reverse=True
        )

        top_3 = ranked[:3]
        confidence = top_3[0][1]

        print(f"Description : {desc}")
        print(f"Actual      : {actual}")
        print(f"Predicted   : {predicted}  (confidence={confidence:.3f})")
        print(f"Top-3       : {top_3}")
        print("-" * 70)

    return vectorizer, model


# --------------------------------------------------
# 4. Run Training
# --------------------------------------------------
if __name__ == "__main__":
    all_data = json.load(open("data.json"))
    for bank_id,data in all_data.items() :
        print(bank_id,len(data))
        if len(data) < 10 : 
            continue
        data = [ (desc,f"{company}/{party_id}") for (desc,company,party_id) in data ]
        vectorizer, model = train_tfidf_logistic(data)
        joblib.dump(vectorizer, f"tfidf_vectorizer_{bank_id}.joblib")
        joblib.dump(model, f"party_classifier_{bank_id}.joblib")
        print(f"Model and vectorizer saved for bank {bank_id}")
