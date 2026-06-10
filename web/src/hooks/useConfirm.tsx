"use client"
import { useCallback, useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface ConfirmDialogProps {
  open: boolean
  message: string
  onConfirm: () => void
  onCancel: () => void
}

function ConfirmDialog({ open, message, onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(o: boolean) => {
        if (!o) onCancel()
      }}
    >
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Confirm action</DialogTitle>
          <DialogDescription>{message}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            onClick={onConfirm}
            className="bg-[var(--danger)] text-white hover:opacity-90"
          >
            Confirm
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function useConfirm() {
  const [dialogState, setDialogState] = useState({ open: false, message: "" })
  const resolveRef = useRef<(value: boolean) => void>(() => {})

  function confirm(message: string): Promise<boolean> {
    return new Promise((resolve) => {
      resolveRef.current = resolve
      setDialogState({ open: true, message })
    })
  }

  useEffect(() => {
    return () => {
      resolveRef.current(false)
    }
  }, [])

  const handleConfirm = useCallback(() => {
    setDialogState((s) => ({ ...s, open: false }))
    resolveRef.current(true)
  }, [])

  const handleCancel = useCallback(() => {
    setDialogState((s) => ({ ...s, open: false }))
    resolveRef.current(false)
  }, [])

  const confirmPortal = (
    <ConfirmDialog
      open={dialogState.open}
      message={dialogState.message}
      onConfirm={handleConfirm}
      onCancel={handleCancel}
    />
  )

  return { confirm, confirmPortal }
}
