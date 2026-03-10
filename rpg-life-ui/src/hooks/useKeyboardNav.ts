import { useEffect } from "react";

export interface KeyboardShortcut {
  key: string;
  ctrlKey?: boolean;
  shiftKey?: boolean;
  callback: () => void;
  description: string;
}

export function useKeyboardShortcuts(shortcuts: KeyboardShortcut[]) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Don't fire shortcuts when user is typing in an input/textarea
      const target = event.target as HTMLElement;
      const isEditable =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable;

      if (isEditable) return;

      shortcuts.forEach(({ key, ctrlKey, shiftKey, callback }) => {
        const ctrlMatch = ctrlKey === undefined || event.ctrlKey === ctrlKey;
        const shiftMatch = shiftKey === undefined || event.shiftKey === shiftKey;

        if (event.key === key && ctrlMatch && shiftMatch) {
          event.preventDefault();
          callback();
        }
      });
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [shortcuts]);
}
