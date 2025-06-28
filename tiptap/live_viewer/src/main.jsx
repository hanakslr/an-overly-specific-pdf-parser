import React, { useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import { useEditor, EditorContent } from '@tiptap/react'
import { extensions } from './extensions';

const Editor = () => {
  const editor = useEditor({
    extensions: extensions,
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
