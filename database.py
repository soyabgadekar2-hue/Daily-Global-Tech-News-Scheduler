from pymongo import MongoClient
from pymongo.errors import PyMongoError

from config import DATABASE_NAME, MONGODB_URI

# Reuse one client instead of opening a new connection for each operation.
client = None


def connect_to_mongodb():
    """Ping MongoDB and return the configured database."""
    global client

    try:
        if client is None:
            client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)

        # MongoClient connects lazily, so ping checks the server is reachable.
        client.admin.command("ping")
        return client[DATABASE_NAME]
    except PyMongoError:
        # Do not include the original exception; it can contain connection details.
        raise ConnectionError(
            "Could not connect to MongoDB. Check that the server is running "
            "and the configured connection settings are correct."
        ) from None


def prepare_collections():
    """Return the required collections after creating their unique indexes."""
    database = connect_to_mongodb()

    try:
        news_collection = database["news"]
        briefings_collection = database["daily_briefings"]

        # Unique indexes prevent duplicate article URLs and briefing dates.
        news_collection.create_index("url", unique=True)
        briefings_collection.create_index("briefing_date", unique=True)

        return news_collection, briefings_collection
    except PyMongoError:
        raise RuntimeError(
            "Could not prepare MongoDB collections or indexes. Check database "
            "permissions and whether existing records contain duplicate values."
        ) from None
