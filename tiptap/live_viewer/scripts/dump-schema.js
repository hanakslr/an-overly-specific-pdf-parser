import { JSDOM } from "jsdom";
const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>");
global.window = dom.window;
global.document = dom.window.document;
global.Node = window.Node;
global.DOMParser = window.DOMParser;

import { Editor } from "@tiptap/core";
import { extensions } from "../src/extensions.js";
import fs from "fs";
import path from "path";

const editor = new Editor({
  extensions: extensions,
});

function pairsFromFlat(array) {
  const result = []
  for (let i = 0; i < array.length; i += 2) {
    result.push([array[i], array[i + 1]])
  }
  return result
}

function dumpSpecMap(map) {
  const items = pairsFromFlat(map.content);
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

const outputPath = path.resolve(process.cwd(), '../editor_schema.json');
fs.writeFileSync(outputPath, JSON.stringify(schemaJSON, null, 2));

console.log(`✅ Schema written to ${outputPath}`); 