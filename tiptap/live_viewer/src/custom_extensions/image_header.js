import { Node, mergeAttributes } from '@tiptap/core'

// export interface ImageRowOptions {
//   HTMLAttributes: Record<string, any>
// }

export const ImageHeader = Node.create({
  name: 'imageHeader',

  group: 'block',

  content: 'image image image', // 3 image nodes, exactly

  parseHTML() {
    return [
      {
        tag: 'div[data-type="image-row"]',
      },
    ]
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'div',
      mergeAttributes(HTMLAttributes, { 'data-type': 'image-row', style: 'display: flex; gap: 8px;' }),
      0, // The child images will be rendered here
    ]
  },

  addAttributes() {
    return {}
  },
})
