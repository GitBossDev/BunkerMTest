'use client'

import * as React from 'react'
import { Info } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

interface InfoTooltipProps {
  content: React.ReactNode
  side?: 'top' | 'right' | 'bottom' | 'left'
  className?: string
}

export function InfoTooltip({ content, side = 'left', className }: InfoTooltipProps) {
  return (
    <TooltipProvider delayDuration={250}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className={cn(
              'inline-flex items-center justify-center rounded-full text-muted-foreground/60 hover:text-muted-foreground transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
              className
            )}
            aria-label="Más información"
          >
            <Info className="h-3.5 w-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent
          side={side}
          className={cn(
            'z-50 max-w-[280px] rounded-lg border border-border bg-popover px-3 py-2.5',
            'text-popover-foreground shadow-md',
            // override the default bg-primary from the base component
            'bg-popover text-popover-foreground'
          )}
        >
          <div className="text-xs leading-relaxed space-y-1.5">{content}</div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

/** Helper: fila de definición para usar dentro del tooltip */
export function TipRow({ label, text }: { label: string; text: string }) {
  return (
    <p>
      <span className="font-semibold text-foreground">{label}:</span>{' '}
      <span className="text-muted-foreground">{text}</span>
    </p>
  )
}
