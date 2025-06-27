import { JSDOM } from "jsdom";
const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>");
global.window = dom.window;
global.document = dom.window.document;
global.Node = window.Node;
global.DOMParser = window.DOMParser;

import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Image from '@tiptap/extension-image'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import fs from "fs";

const editor = new Editor({
  extensions: [StarterKit, Image, Table, TableRow, TableCell, TableHeader],
});

function pairsFromFlat(array) {
  const result = []
  for (let i = 0; i < array.length; i += 2) {
    result.push([array[i], array[i + 1]])
  }
  return result
}

function dumpSpecMap(map) {
  console.log(map.content);
  const items = pairsFromFlat(map.content);
  console.log(items)
  return Object.fromEntries(
    items.map(([name, item]) => [
      name,
      {
        group: item.group ?? null,
        content: item.content ?? null,
        marks: item.marks ?? null,
        attrs: item.attrs ?? {},
        defining: item.defining ?? false,
      },
    ])
  );
}

const schemaJSON = {
  nodes: dumpSpecMap(editor.schema.spec.nodes),
  marks: dumpSpecMap(editor.schema.spec.marks),
};

fs.writeFileSync("../editor_schema.json", JSON.stringify(schemaJSON, null, 2));
