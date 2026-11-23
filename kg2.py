import pandas as pd
import re
from neo4j import GraphDatabase
import spacy

# Load NLP model for entity recognition
nlp = spacy.load("en_core_web_sm")

# Neo4j config
NEO4J_URI = "neo4j+s://21347e0a.databases.neo4j.io"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "sTQGBMUXIprfq--hZJ-1GIuPVguUTUG90JRzA6BP-ss"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# -----------------------------
# Extract entities with type
# -----------------------------
def extract_entities(text):

    persons = []
    locations = []
    orgs = []
    movies = []

    if pd.isna(text):
        return persons, locations, orgs, movies

    doc = nlp(str(text))

    for ent in doc.ents:

        label = ent.label_
        entity = ent.text.strip()

        if label == "PERSON":
            persons.append(entity)

        elif label in ["GPE", "LOC"]:
            locations.append(entity)

        elif label == "ORG":
            orgs.append(entity)

        elif label == "WORK_OF_ART":

            # Only treat as movie if question contains movie context
            if any(word in text.lower() for word in
                   ["movie","movies","film","actor","actress","director","played","role","star","starring"]):
                movies.append(entity)

    return persons, locations, orgs, movies


# -----------------------------
# Import data into Neo4j
# -----------------------------
def import_row(tx, row_id, url, question,
               persons, locations, orgs, movies,answer_text):

    # Create URL node
    tx.run(
        "MERGE (u:URL {name:$url})",
        url=url
    )

    # Create Question node
    tx.run(
        """
        MERGE (q:Question {id:$id})
        SET q.text=$text
        """,
        id=row_id,
        text=question
    )
    # -----------------------------
    # ANSWER node
    # -----------------------------
    tx.run(
        """
        MERGE (a:Answer {text:$answer})
        """,
        answer=answer_text
    )
    tx.run(
        """
        MATCH (q:Question {id:$id})
        MATCH (a:Answer {text:$answer})
        MERGE (q)-[:ANSWERS_WITH]->(a)
        """,
        id=row_id,
        answer=answer_text
    )
    # Ensure question connects to only one URL
    tx.run(
        """
        MATCH (q:Question {id:$id})-[r:FROM_URL]->()
        DELETE r
        """,
        id=row_id
    )

    tx.run(
        """
        MATCH (q:Question {id:$id})
        MATCH (u:URL {name:$url})
        MERGE (q)-[:FROM_URL]->(u)
        """,
        id=row_id,
        url=url
    )

    # -----------------------------
    # PERSON entities
    # -----------------------------
    for p in persons:

        tx.run(
            "MERGE (n:Person {name:$name})",
            name=p
        )

        tx.run(
            """
            MATCH (q:Question {id:$id})
            MATCH (n:Person {name:$name})
            MERGE (q)-[:ABOUT_PERSON]->(n)
            """,
            id=row_id,
            name=p
        )

    # -----------------------------
    # LOCATION entities
    # -----------------------------
    for l in locations:

        tx.run(
            "MERGE (n:Location {name:$name})",
            name=l
        )

        tx.run(
            """
            MATCH (q:Question {id:$id})
            MATCH (n:Location {name:$name})
            MERGE (q)-[:ABOUT_LOCATION]->(n)
            """,
            id=row_id,
            name=l
        )

    # -----------------------------
    # ORGANIZATION entities
    # -----------------------------
    for o in orgs:

        tx.run(
            "MERGE (n:Organization {name:$name})",
            name=o
        )

        tx.run(
            """
            MATCH (q:Question {id:$id})
            MATCH (n:Organization {name:$name})
            MERGE (q)-[:ABOUT_ORG]->(n)
            """,
            id=row_id,
            name=o
        )

    # -----------------------------
    # MOVIE entities
    # -----------------------------
    for m in movies:

        tx.run(
            "MERGE (n:Movie {name:$name})",
            name=m
        )

        tx.run(
            """
            MATCH (q:Question {id:$id})
            MATCH (n:Movie {name:$name})
            MERGE (q)-[:ABOUT_MOVIE]->(n)
            """,
            id=row_id,
            name=m
        )




# -----------------------------
# Load dataset
# -----------------------------
print("Loading dataset...")

df = pd.read_csv("test.csv")

print("Rows:", df.shape[0])


# -----------------------------
# Insert data
# -----------------------------
with driver.session() as session:

    for idx, row in df.iterrows():

        url_entity = "Unknown"

        if pd.notna(row['url']):
            match = re.search(r'/view/(.+)/?$', str(row['url']))
            if match:
                url_entity = match.group(1).replace("_", " ").title()

        question_text = str(row['question'])
        answer_text = str(row['answers'])

        # Classify the question itself, not the answer text, so movie links
        # only reflect what the question is actually about.
        persons, locations, orgs, movies = extract_entities(question_text)

        session.execute_write(
            import_row,
            idx,
            url_entity,
            question_text,
            persons,
            locations,
            orgs,
            movies,
            answer_text
        )

        if idx % 200 == 0:
            print("Imported:", idx)


driver.close()

print("Import Completed")