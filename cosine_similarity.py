from sentence_transformers import SentenceTransformer, util
import regex as re
def preprocess_text(text):
    """
    Basic text preprocessing: lowercase and split into words (tokens).
    Optionally, add stopword removal or stemming here based on Sec 2.4
    of the paper.
    """
    if not text:
        return []
    # Remove simple HTML tags (very basic, not robust)
    text = re.sub(r'<[^>]+>', ' ', text)
    # Find words (sequences of alphanumeric characters)
    words = re.findall(r'\b\w+\b', text.lower())
    # Simple stopword list (can be expanded)
    stopwords = {'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
                 'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
                 'to', 'was', 'were', 'will', 'with', 'jobs', 'job', 'career',
                 'careers'} # Added common job words to avoid them dominating if in query
    words = " ".join([word for word in words if word not in stopwords and len(word) > 1])
    # words=" ".join(word for word in words)
    return words

async def calculate_cosine_similarity_score(markdown : str):
# Load a pre-trained sentence embedding model
    model = SentenceTransformer('all-MiniLM-L6-v2')


    job_listing_topic_description =f"""
    This page contains a structured list of job opportunities offered by a company or organization.
    It includes job titles, brief descriptions, application links, departments, locations, and sometimes filters for role, location, or experience.
    The page may also include pagination, sorting options, and links to apply or view more details about each position.
    """
    processed_markdown=preprocess_text(markdown)
    # processed_markdown=markdown
    # print("processed_markdown",processed_markdown)
    # Get embeddings
    embedding1 = model.encode(job_listing_topic_description, convert_to_tensor=True)
    embedding2 = model.encode(processed_markdown, convert_to_tensor=True)

    # Compute cosine similarity
    cos_sim = util.pytorch_cos_sim(embedding1, embedding2)

    # print(f"Cosine Similarity (Embedding): {cos_sim.item():.4f}")
    return cos_sim
