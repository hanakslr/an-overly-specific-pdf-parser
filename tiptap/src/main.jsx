import React, { useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'

const Editor = () => {
  const editor = useEditor({
    extensions: [StarterKit, Image, Table, TableRow, TableCell, TableHeader],
    content: '',
  })

  useEffect(() => {
    const interval = setInterval(async () => {
      const res = await fetch('/api/get-doc')
      const data = await res.json()
      if (editor && data.content) {
        editor.commands.setContent(data.content)
      }
    }, 1000)
    return () => clearInterval(interval)
  }, [editor])

  return <EditorContent editor={editor} />
}

ReactDOM.createRoot(document.getElementById('root')).render(<Editor />)
