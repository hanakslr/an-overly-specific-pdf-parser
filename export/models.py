from peewee import (
    SQL,
    BigIntegerField,
    DateTimeField,
    ForeignKeyField,
    Model,
    TextField,
    UUIDField,
)
from playhouse.postgres_ext import BinaryJSONField, PostgresqlDatabase

database = PostgresqlDatabase(
    "postgres",
    **{"host": "localhost", "port": 54322, "user": "postgres", "password": "postgres"},
)


class UnknownField(object):
    def __init__(self, *_, **__):
        pass


class BaseModel(Model):
    class Meta:
        database = database


class Collections(BaseModel):
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    id = UUIDField(constraints=[SQL("DEFAULT gen_random_uuid()")], primary_key=True)
    name = TextField()

    class Meta:
        table_name = "collections"


class BlockSchemas(BaseModel):
    collection = ForeignKeyField(
        column_name="collection_id", field="id", model=Collections, null=True
    )
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    id = UUIDField(constraints=[SQL("DEFAULT gen_random_uuid()")], primary_key=True)
    schema = BinaryJSONField()
    updated_at = DateTimeField(constraints=[SQL("DEFAULT now()")])

    class Meta:
        table_name = "block_schemas"


class Documents(BaseModel):
    collection = ForeignKeyField(
        column_name="collection_id", field="id", model=Collections
    )
    collection_index = BigIntegerField()
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    id = UUIDField(constraints=[SQL("DEFAULT gen_random_uuid()")], primary_key=True)
    label = TextField(null=True)
    slug = TextField()
    title = TextField()
    cover_image = TextField()

    class Meta:
        table_name = "documents"


class Blocks(BaseModel):
    attrs = BinaryJSONField(null=True)
    content = BinaryJSONField(null=True)
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    document = ForeignKeyField(column_name="document_id", field="id", model=Documents)
    document_index = BigIntegerField()
    id = UUIDField(constraints=[SQL("DEFAULT gen_random_uuid()")], primary_key=True)
    next_block = ForeignKeyField(
        column_name="next_block_id", field="id", model="self", null=True
    )
    prev_block = ForeignKeyField(
        backref="blocks_prev_block_set",
        column_name="prev_block_id",
        field="id",
        model="self",
        null=True,
    )
    text = TextField(null=True)
    type = TextField()

    class Meta:
        table_name = "blocks"
