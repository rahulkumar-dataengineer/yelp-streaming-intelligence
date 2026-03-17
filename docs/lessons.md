# Lessons Learned

## Bronze field names: use underscores, not dots
Bronze Parquet column names originally used dots (`attributes.BikeParking`, `hours.Monday`) which conflicts with Spark's nested field access syntax and requires backtick escaping everywhere. Changed to underscores (`attributes_BikeParking`, `hours_Monday`). Rule: never use dots in flat Parquet column names.

## No regex for data parsing — use deterministic code
For parsing Python literal strings (`u'none'`, `{'garage': True}`) in the Yelp dataset, use `ast.literal_eval` via PySpark UDFs instead of regex patterns. `ast.literal_eval` is Python's built-in parser for literals — it handles all edge cases (u-prefix, None, partial dicts) deterministically. Regex is fragile and hard to maintain for nested structures.

## Partition columns are not in Parquet file data
When Spark writes with `partitionBy("col")`, the column is removed from the Parquet file and encoded in directory names only. When reading these files back in a downstream streaming layer, the partition column won't be in the file data. Solution: exclude the partition column from the read schema and re-derive it (e.g., `ingestion_date` from `ingestion_timestamp`). Note: with Hive Metastore managed tables, partition columns are handled automatically — no manual schema exclusion needed.

## Hive Metastore: `USING parquet` must be lowercase
Spark's streaming `toTable()` writer internally uses `parquet` (lowercase) as the data source name. If the DDL creates the table with `USING PARQUET` (uppercase), Spark does a case-sensitive comparison and throws `The input source(parquet) is different from the table's data source provider(PARQUET)`. Always use `USING parquet` (lowercase) in DDL for Spark data source tables.

## Hive Metastore: database locations are set at creation time
`CREATE DATABASE IF NOT EXISTS` is a no-op for existing databases — it does NOT update the warehouse location. If you change `spark.sql.warehouse.dir` after databases already exist, you must `DROP DATABASE CASCADE` and recreate them for the new path to take effect.

## Hive Metastore: shared filesystem for managed tables
When Spark runs locally but the Hive Metastore runs in Docker, managed table directories must be accessible from both. Use a shared path like `/tmp/spark-warehouse` and mount it as a Docker volume. Without this, the metastore throws `MetaException: ... is not a directory or unable to create one`.

## Hive Metastore: remove `.format()` when using `toTable()`
When writing to a Hive-managed table via `writeStream.toTable(tableName)`, do not set `.format("parquet")` explicitly. The format is inferred from the table's metadata in the metastore. Setting it explicitly can cause provider mismatch errors.

## ChatGoogleGenerativeAI: `thinking_level` changes response.content type
When `thinking_level` is set on `ChatGoogleGenerativeAI` (langchain-google-genai), `response.content` returns a `list` of content block dicts (`[{"type": "text", "text": "..."}]`) instead of a plain `str`. This also affects `create_sql_agent` output. Always use a normalizer like `extract_text(content)` that handles both formats. Set `thinking_level` as a constructor param, not via `model_kwargs`.
