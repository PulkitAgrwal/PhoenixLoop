"use client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

import { useHealingCycle } from "./healing-cycle-context";

export function DismissWarningDialog() {
  const { dismissWarningOpen, cancelCloseModal, confirmCloseModal } =
    useHealingCycle();

  return (
    <AlertDialog
      open={dismissWarningOpen}
      onOpenChange={(open) => {
        if (!open) cancelCloseModal();
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Cycle still running</AlertDialogTitle>
          <AlertDialogDescription>
            Closing the modal won&apos;t stop the healing cycle. Progress
            continues in the background and you can reopen it from the chip in
            the bottom-right corner.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={cancelCloseModal}>
            Keep watching
          </AlertDialogCancel>
          <AlertDialogAction onClick={confirmCloseModal}>
            Close, leave chip
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
