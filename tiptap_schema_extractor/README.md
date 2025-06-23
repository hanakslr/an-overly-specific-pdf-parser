# Tiptap

Tiptap is a wrapper around ProseMirror. They have a handful of nice extensions that we want to use. In order to export our PDF content to the specific schema of the nodes and marks we are interested in, we need to instantiate the editor and dump them.

To add an extension, add it first to package.json, then to the editor in index.js.
Then run `node index.js`. This will update the editor_schema.json output file.

Then run `uv run tiptap_schema_extractor/generate_prose_mirror_classes.py` and this will update tiptap_models.py with the shape of all of the nodes that are allowed.
