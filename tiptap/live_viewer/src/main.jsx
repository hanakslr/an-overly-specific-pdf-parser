import React, { useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import { useEditor, EditorContent } from '@tiptap/react'
import { extensions } from './extensions';

const API_URL = 'http://localhost:8000';

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
        // Recursively go through data.content and prepend API_URL to image src
        const updatedContent = {
          ...data.content,
          content: data.content.content.map((node) => {
            if (node.type === 'image' && node.attrs.src) {
              return {
                ...node,
                attrs: {
                  ...node.attrs,
                  src: `${API_URL}/images/${node.attrs.src}`,
                },
              };
            }
            return node;
          }),
        };
        editor.commands.setContent(updatedContent)
      }
    }, 1000)
    return () => clearInterval(interval)
  }, [editor])

  return <EditorContent editor={editor} />
}

ReactDOM.createRoot(document.getElementById('root')).render(<Editor />)
