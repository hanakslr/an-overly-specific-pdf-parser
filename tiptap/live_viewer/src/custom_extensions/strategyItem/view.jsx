import React from 'react'
import { NodeViewContent, NodeViewWrapper } from '@tiptap/react'

export const StrategyItemView = ({ node, updateAttributes }) => {
  const { label } = node.attrs

  const handleLabelChange = (e) => {
    updateAttributes({ label: e.target.value })
  }

  return (
    <NodeViewWrapper as="div" className="p-6 border-2 border-plan-blue-200 rounded-lg bg-plan-blue-50 shadow-sm mb-4">
      {/* Strategy Label Header */}
      <div className="mb-4 border-b border-plan-blue-200 pb-3">
        <input
          type="text"
          value={label}
          onChange={handleLabelChange}
          className="text-xl font-bold text-plan-blue-700 bg-transparent border-none outline-none focus:bg-white focus:border focus:border-plan-blue-300 focus:rounded px-2 py-1 w-full"
          placeholder="Strategy Label"
        />
      </div>

      {/* Strategy Content */}
      <div className="space-y-4">
        {/* This will render the paragraph and action items */}
        <NodeViewContent className="strategy-content" />
      </div>

      {/* Visual separator for nested action items */}
      <style jsx>{`
        .strategy-content [data-type="action-item"] {
          margin-left: 1rem;
          border-left: 3px solid #3b82f6;
          padding-left: 1rem;
          margin-top: 0.75rem;
        }
        .strategy-content p {
          margin-bottom: 1rem;
          font-size: 1rem;
          line-height: 1.6;
          color: #374151;
        }
      `}</style>
    </NodeViewWrapper>
  )
} 