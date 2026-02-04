# categorization.py
import re
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet



# Ensure necessary NLTK data is downloaded
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')
nltk.download('punkt_tab')
nltk.download("averaged_perceptron_tagger")


# Predefined categories
PREDEFINED_CATEGORIES = ["Mood", "Activity", "Idea", "Task", "Health", "Social", "Work", "Other"]

def get_wordnet_pos(tag):
    """
    Map POS tag to the format accepted by WordNetLemmatizer.
    :param tag: POS tag from NLTK's pos_tag.
    :return: WordNet POS tag (or 'n' by default for nouns).
    """
    if tag.startswith("J"):
        return wordnet.ADJ
    elif tag.startswith("V"):
        return wordnet.VERB
    elif tag.startswith("N"):
        return wordnet.NOUN
    elif tag.startswith("R"):
        return wordnet.ADV
    else:
        return wordnet.NOUN

def extract_keywords(entry_content: str) -> list[str]:
    """
    Extract significant keywords from journal content.
    Combines advanced tokenization, case normalization, special character removal,
    stop word removal, and lemmatization with POS tagging for better precision.
    
    :param entry_content: The text content of the journal entry.
    :return: List of significant keywords.
    """
    # Normalize case
    entry_content = entry_content.lower()
    
    # Remove special characters
    entry_content = re.sub(r'[^\w\s]', '', entry_content)
    
    # Tokenize the content
    tokens = word_tokenize(entry_content)
    
    # Custom stop words (extending the default list)
    stop_words = set(stopwords.words("english")).union({"went", "get", "like", "feel"})
    
    # Remove stop words
    filtered_tokens = [token for token in tokens if token not in stop_words]
    
    # Lemmatize the tokens with POS tagging
    lemmatizer = WordNetLemmatizer()
    pos_tags = nltk.pos_tag(filtered_tokens)
    lemmatized_tokens = [
        lemmatizer.lemmatize(token, get_wordnet_pos(tag)) for token, tag in pos_tags
    ]
    
    # Remove single-character tokens (e.g., "a", "I") except for meaningful words like "i"
    meaningful_tokens = [token for token in lemmatized_tokens if len(token) > 1]
    
    return meaningful_tokens


def map_keywords_to_categories(keywords: list[str]) -> list[str]:
    """
    Map extracted keywords to predefined categories.
    :param keywords: List of extracted keywords.
    :return: List of suggested categories based on keyword matches.
    """
    suggested_categories = []
    
    # Define keyword to category mapping
    keyword_category_map = {
        "happy": "Mood",
        "sad": "Mood",
        "run": "Activity",
        "exercise": "Activity",
        "idea": "Idea",
        "task": "Task",
        "health": "Health",
        "friend": "Social",
        "work": "Work",
        # Add more mappings as needed
    }
    
    for keyword in keywords:
        category = keyword_category_map.get(keyword.lower())
        if category and category not in suggested_categories:
            suggested_categories.append(category)
    
    if not suggested_categories:
        suggested_categories.append("Other")
    
    return suggested_categories

def get_categories(entry_content: str) -> list[str]:
    """
    Suggest categories based on the content of the journal entry.
    :param entry_content: The text content of the journal entry.
    :return: List of suggested categories.
    """
    keywords = extract_keywords(entry_content)
    suggested_categories = map_keywords_to_categories(keywords)
    return suggested_categories