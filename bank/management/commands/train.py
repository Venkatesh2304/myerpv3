import json
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import numpy as np

# 1. Cleaning Function (Matches your Postgres Logic)
def clean_text(text):
    text = text.upper()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def train_and_test_mapper(data_list):
    """
    data_list: list of [description, party_code]
    """
    # Pre-process
    descriptions = [clean_text(row[0]) for row in data_list]
    party_codes = [row[1] for row in data_list]

    # 2. Split into Training and Testing (80/20 split)
    X_train, X_test, y_train, y_test = train_test_split(
        descriptions, party_codes, test_size=0.2, random_state=42
    )

    # 3. Vectorize using Character N-Grams
    # We use char-level (3-6 chars) to catch '5 STAR' inside long strings
    # vectorizer = TfidfVectorizer(analyzer='word', ngram_range=(1,2))
    vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(3, 6))
    train_vectors = vectorizer.fit_transform(X_train)
    test_vectors = vectorizer.transform(X_test)

    # 4. Define Predictor (Finding the most similar training example)
    def predict(input_vectors):
        predictions = []
        # Calculate cosine similarity between test items and all training items
        similarities = cosine_similarity(input_vectors, train_vectors)
        
        for row in similarities:
            # Find the index of the highest similarity score
            best_match_idx = row.argmax()
            predictions.append(y_train[best_match_idx])
        return predictions

    # 5. Calculate Scores
    train_preds = predict(train_vectors)
    test_preds = predict(test_vectors)


    # 2. Calculate similarity between Test descriptions and ALL Training descriptions
    similarities = cosine_similarity(test_vectors, train_vectors)
    print(f"{'BANK DESCRIPTION':<45} | {'ACTUAL':<15} | {'TOP 3 MATCH?'} | {'TOP SCORE'}")
    print("-" * 100)

    for i in range(len(X_test)):
        row_scores = similarities[i]
        
        # 1. Get the indices of the TOP 3 highest scores
        # argsort sorts ascending, so we take the last 3 elements and reverse them
        top_3_indices = np.argsort(row_scores)[-3:][::-1]
        
        # 2. Get the labels (Party Names) for those top 3 indices
        top_3_labels = [y_train[idx] for idx in top_3_indices]
        top_3_scores = [row_scores[idx] for idx in top_3_indices]
        
        actual_party = y_test[i]
        
        # 3. Check if actual_party is anywhere in the top 3
        is_top_3_match = "YES" if actual_party in top_3_labels else "NO  <--"
        
        # Print the result
        # We show the highest score (Top 1) for reference
        print(f"{X_test[i]:<45} | {actual_party:<15} | {is_top_3_match:<12} | {top_3_scores[0]:.4f}")

        # Optional: If you want to see what the top 3 were when it fails
        if actual_party not in top_3_labels:
            print(f"    Suggested were: {top_3_labels}")

    train_score = accuracy_score(y_train, train_preds)
    test_score = accuracy_score(y_test, test_preds)

    print(f"Training Accuracy: {train_score * 100:.2f}%")
    print(f"Testing Accuracy: {test_score * 100:.2f}%")

    return vectorizer, train_vectors, y_train

# Example Usage with your data
data = json.load(open("data.json"))
data = [ i for i in data if not "CREDIT-CHQ" in i[0].upper()]

# Run it
vectorizer, trained_matrix, trained_labels = train_and_test_mapper(data)