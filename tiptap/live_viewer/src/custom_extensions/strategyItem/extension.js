// extensions/StrategyItem.js
import { Node, mergeAttributes } from '@tiptap/core'
import { ReactNodeViewRenderer } from '@tiptap/react'

let StrategyItemView

if (typeof window !== 'undefined') {
  // Load it dynamically once, outside `addNodeView`
  StrategyItemView = (await import('./view.jsx')).StrategyItemView
}

export const StrategyItem = Node.create({
  name: 'strategyItem',

  group: 'block',
  content: 'paragraph actionItem*', // paragraph followed by zero or more action items

  selectable: true,
  isolating: true, // prevents weird merge behaviors

  addAttributes() {
    return {
      label: { 
        default: '',
        parseHTML: element => element.getAttribute('data-label'),
        renderHTML: attributes => ({
          'data-label': attributes.label,
        }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="strategy-item"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'strategy-item' }), 0]
  },

  addNodeView() {
    if (!StrategyItemView) return null
    return ReactNodeViewRenderer(StrategyItemView)
  },
}) 