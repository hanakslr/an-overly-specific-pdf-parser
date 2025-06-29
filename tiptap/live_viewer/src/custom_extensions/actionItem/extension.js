// extensions/ActionItem.ts
import { Node, mergeAttributes } from '@tiptap/core'
import { ReactNodeViewRenderer } from '@tiptap/react'

let ActionItemView

if (typeof window !== 'undefined') {
  // Load it dynamically once, outside `addNodeView`
  ActionItemView = (await import('./view.jsx')).ActionItemView
}

export const ActionItem = Node.create({
  name: 'actionItem',

  group: 'block',
  content: 'paragraph', // editable text

  selectable: true,
  isolating: true, // prevents weird merge behaviors

  addAttributes() {
    return {
      strategy: { default: '' },
      label: { default: '' },
      responsibility: { default: '' },
      timeframe: { default: '' },
      cost: { default: '' },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="action-item"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'action-item' }), 0]
  },

  addNodeView() {
    if (!ActionItemView) return null
    return ReactNodeViewRenderer(ActionItemView)
  },
})
