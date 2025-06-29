// extensions/ActionItemView.jsx
import React from 'react'
import { NodeViewContent, NodeViewWrapper } from '@tiptap/react'

const ActionBadge = ({type, value}) => {
    return (<div>{value}</div>)
}
export const ActionItemView = ({ node }) => {
  console.log(node.attrs)
  const { label, responsibility, timeframe, cost } = node.attrs

  const responsibilities = responsibility.split('\n').map(r => r.trim())

  return (
    <NodeViewWrapper as="div" className="p-4 border rounded bg-white shadow-sm">
      <div className="mb-4">
        <div className="flex items-center gap-2">
          <span className="text-plan-blue-accent font-bold">{label}</span>
        </div>
        <NodeViewContent as="p" className="mt-2" />
      </div>

      <div className="flex flex-wrap gap-2">
        {responsibilities.map((resp, i) => (
          <ActionBadge
            key={i}
            type="responsibility"
            value={resp}
          />
        ))}
        <ActionBadge
          type="timeframe"
          value={timeframe}
        />
        <ActionBadge
          type="cost"
          value={cost}
        />
      </div>
    </NodeViewWrapper>
  )
}
