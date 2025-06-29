import StarterKit from "@tiptap/starter-kit";
import Image from '@tiptap/extension-image'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import { ImageHeader } from "./custom_extensions/image_header.js";
import {ActionItem} from "./custom_extensions/actionItem/extension.js"

export const extensions = [
    StarterKit,
    Image,
    Table,
    TableRow,
    TableCell,
    TableHeader,
    ImageHeader,
    ActionItem
]; 