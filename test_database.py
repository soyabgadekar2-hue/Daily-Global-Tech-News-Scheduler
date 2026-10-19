from database import connect_to_mongodb, prepare_collections


def main():
    """Check the MongoDB connection and required collection indexes."""
    try:
        database = connect_to_mongodb()
        news_collection, briefings_collection = prepare_collections()

        collection_names = database.list_collection_names()
        if "news" not in collection_names:
            raise RuntimeError("The news collection was not found.")
        if "daily_briefings" not in collection_names:
            raise RuntimeError("The daily_briefings collection was not found.")

        news_index = news_collection.index_information().get("url_1", {})
        briefing_index = briefings_collection.index_information().get(
            "briefing_date_1", {}
        )
        if not news_index.get("unique"):
            raise RuntimeError("The unique news.url index was not found.")
        if not briefing_index.get("unique"):
            raise RuntimeError(
                "The unique daily_briefings.briefing_date index was not found."
            )

        print("MongoDB ping: successful")
        print(f"Database access: {database.name}")
        print("Collections: news, daily_briefings")
        print("Unique indexes: news.url, daily_briefings.briefing_date")
    except (ConnectionError, RuntimeError) as error:
        # These messages are created locally and do not contain connection details.
        print(f"MongoDB test failed: {error}")
        raise SystemExit(1)
    except Exception:
        # Avoid printing raw driver errors, which may contain connection details.
        print(
            "MongoDB test failed. Check that MongoDB is running, the configured "
            "database settings are valid, and the database user can create indexes."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
