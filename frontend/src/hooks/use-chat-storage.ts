"use client";

import * as React from "react";

// ============================================================================
// Types
// ============================================================================

/**
 * Stored message format - timestamps are ISO strings for JSON compatibility
 */
interface StoredMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string; // ISO string, not Date
  response?: unknown; // AskResponse - kept as unknown for storage layer
  isLoading?: boolean;
  error?: string;
}

/**
 * Schema version 1 - initial implementation
 */
interface ChatStorageV1 {
  version: 1;
  messages: StoredMessage[];
  selectedDoc: string;
  lastUpdated: string;
}

/**
 * Runtime message type with proper Date objects
 */
export interface RuntimeMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  response?: unknown;
  isLoading?: boolean;
  error?: string;
}

// ============================================================================
// Constants
// ============================================================================

const STORAGE_KEY = "npr-chat-state";
const CURRENT_VERSION = 1;
const DEBOUNCE_MS = 500;
const MAX_MESSAGES = 100; // Prevent unbounded growth

// ============================================================================
// Storage Availability Check
// ============================================================================

/**
 * Check if localStorage is available and usable
 * Handles: private browsing, SecurityError, disabled storage
 */
function isStorageAvailable(): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  try {
    const testKey = "__npr_storage_test__";
    window.localStorage.setItem(testKey, "test");
    window.localStorage.removeItem(testKey);
    return true;
  } catch {
    return false;
  }
}

// ============================================================================
// Validation
// ============================================================================

/**
 * Type guard for StoredMessage
 */
function isValidStoredMessage(obj: unknown): obj is StoredMessage {
  if (typeof obj !== "object" || obj === null) return false;

  const msg = obj as Record<string, unknown>;

  return (
    typeof msg.id === "string" &&
    (msg.role === "user" || msg.role === "assistant") &&
    typeof msg.content === "string" &&
    typeof msg.timestamp === "string"
  );
}

/**
 * Type guard for ChatStorageV1
 */
function isValidChatStorageV1(obj: unknown): obj is ChatStorageV1 {
  if (typeof obj !== "object" || obj === null) return false;

  const storage = obj as Record<string, unknown>;

  return (
    storage.version === 1 &&
    Array.isArray(storage.messages) &&
    storage.messages.every(isValidStoredMessage) &&
    typeof storage.selectedDoc === "string" &&
    typeof storage.lastUpdated === "string"
  );
}

/**
 * Validate and migrate storage data to current version
 * Returns null if data is irrecoverable
 */
function validateAndMigrate(raw: unknown): ChatStorageV1 | null {
  // Handle version migrations here as schema evolves
  // For now, only v1 exists

  if (isValidChatStorageV1(raw)) {
    return raw;
  }

  // Future: Add migration from older versions
  // if (isValidChatStorageV0(raw)) {
  //   return migrateV0ToV1(raw);
  // }

  return null;
}

// ============================================================================
// Serialization
// ============================================================================

/**
 * Convert runtime messages to storage format
 */
function serializeMessages(messages: RuntimeMessage[]): StoredMessage[] {
  // Limit stored messages to prevent quota issues
  const trimmedMessages = messages.slice(-MAX_MESSAGES);

  return trimmedMessages.map((msg) => ({
    id: msg.id,
    role: msg.role,
    content: msg.content,
    timestamp: msg.timestamp.toISOString(),
    response: msg.response,
    error: msg.error,
    // Explicitly exclude isLoading - doesn't make sense to persist
  }));
}

/**
 * Convert stored messages to runtime format
 */
function deserializeMessages(stored: StoredMessage[]): RuntimeMessage[] {
  return stored.map((msg) => ({
    id: msg.id,
    role: msg.role,
    content: msg.content,
    timestamp: new Date(msg.timestamp),
    response: msg.response,
    error: msg.error,
    // Ensure loading is false for restored messages
    isLoading: false,
  }));
}

// ============================================================================
// Storage Operations
// ============================================================================

/**
 * Load chat state from localStorage
 * Returns null if storage unavailable or data invalid
 */
function loadFromStorage(): {
  messages: RuntimeMessage[];
  selectedDoc: string;
} | null {
  if (!isStorageAvailable()) {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);

    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw);
    const validated = validateAndMigrate(parsed);

    if (!validated) {
      // Data is corrupted - clear it
      console.warn("[useChatStorage] Invalid storage data, clearing");
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }

    return {
      messages: deserializeMessages(validated.messages),
      selectedDoc: validated.selectedDoc,
    };
  } catch (error) {
    // JSON parse error or other issue
    console.warn("[useChatStorage] Failed to load storage:", error);

    // Clear corrupted data
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore removal errors
    }

    return null;
  }
}

/**
 * Save chat state to localStorage
 * Returns true if successful, false otherwise
 */
function saveToStorage(
  messages: RuntimeMessage[],
  selectedDoc: string
): boolean {
  if (!isStorageAvailable()) {
    return false;
  }

  const storage: ChatStorageV1 = {
    version: CURRENT_VERSION,
    messages: serializeMessages(messages),
    selectedDoc,
    lastUpdated: new Date().toISOString(),
  };

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(storage));
    return true;
  } catch (error) {
    // Quota exceeded or other error
    console.warn("[useChatStorage] Failed to save:", error);

    // Try to save with fewer messages
    if (messages.length > 10) {
      const reducedStorage: ChatStorageV1 = {
        ...storage,
        messages: serializeMessages(messages.slice(-10)),
      };

      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(reducedStorage));
        console.info(
          "[useChatStorage] Saved reduced message history due to quota"
        );
        return true;
      } catch {
        // Still failed - give up
      }
    }

    return false;
  }
}

/**
 * Clear chat state from localStorage
 */
function clearStorage(): void {
  if (!isStorageAvailable()) {
    return;
  }

  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore errors
  }
}

// ============================================================================
// Hook
// ============================================================================

export interface UseChatStorageOptions {
  /**
   * List of valid document IDs - used to validate selectedDoc on load
   * If selectedDoc is not in this list, it will be reset to default
   */
  validDocIds?: string[];

  /**
   * Default selected document value
   */
  defaultSelectedDoc?: string;
}

export interface UseChatStorageReturn {
  /** Current messages */
  messages: RuntimeMessage[];

  /** Update messages (triggers debounced save) */
  setMessages: React.Dispatch<React.SetStateAction<RuntimeMessage[]>>;

  /** Currently selected document */
  selectedDoc: string;

  /** Update selected document (triggers save) */
  setSelectedDoc: (docId: string) => void;

  /** Clear all storage and reset to defaults */
  clearChat: () => void;

  /** Whether storage is available */
  storageAvailable: boolean;

  /** Whether initial load is complete */
  isHydrated: boolean;
}

export function useChatStorage(
  options: UseChatStorageOptions = {}
): UseChatStorageReturn {
  const { validDocIds = [], defaultSelectedDoc = "__all__" } = options;

  // State
  const [messages, setMessagesInternal] = React.useState<RuntimeMessage[]>([]);
  const [selectedDoc, setSelectedDocInternal] =
    React.useState(defaultSelectedDoc);
  const [isHydrated, setIsHydrated] = React.useState(false);
  const [storageAvailable] = React.useState(() => isStorageAvailable());

  // Refs for debouncing
  const debounceTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(
    null
  );
  const pendingStateRef = React.useRef<{
    messages: RuntimeMessage[];
    selectedDoc: string;
  } | null>(null);

  // Track current selectedDoc in a ref for use in callbacks
  const selectedDocRef = React.useRef(selectedDoc);
  selectedDocRef.current = selectedDoc;

  // Track current messages in a ref for use in callbacks
  const messagesRef = React.useRef(messages);
  messagesRef.current = messages;

  // Load from storage on mount (client-side only)
  React.useEffect(() => {
    const stored = loadFromStorage();

    if (stored) {
      setMessagesInternal(stored.messages);

      // Validate selectedDoc against current document list
      // Note: validDocIds may be empty on first render, we'll re-validate later
      setSelectedDocInternal(stored.selectedDoc);
    }

    setIsHydrated(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run on mount

  // Re-validate selectedDoc when validDocIds changes (after docs load)
  React.useEffect(() => {
    if (!isHydrated || validDocIds.length === 0) return;

    if (
      selectedDoc !== defaultSelectedDoc &&
      !validDocIds.includes(selectedDoc)
    ) {
      // Selected doc was deleted
      console.info(
        "[useChatStorage] Selected document no longer exists, resetting"
      );
      setSelectedDocInternal(defaultSelectedDoc);
      // Save immediately to persist the reset
      saveToStorage(messagesRef.current, defaultSelectedDoc);
    }
  }, [validDocIds, isHydrated, selectedDoc, defaultSelectedDoc]);

  // Debounced save function
  const debouncedSave = React.useCallback(
    (msgs: RuntimeMessage[], doc: string) => {
      // Store pending state
      pendingStateRef.current = { messages: msgs, selectedDoc: doc };

      // Clear existing timer
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }

      // Set new timer
      debounceTimerRef.current = setTimeout(() => {
        if (pendingStateRef.current) {
          saveToStorage(
            pendingStateRef.current.messages,
            pendingStateRef.current.selectedDoc
          );
          pendingStateRef.current = null;
        }
      }, DEBOUNCE_MS);
    },
    []
  );

  // Flush pending saves on unmount
  React.useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }

      // Flush any pending state
      if (pendingStateRef.current) {
        saveToStorage(
          pendingStateRef.current.messages,
          pendingStateRef.current.selectedDoc
        );
      }
    };
  }, []);

  // Wrapped setMessages that triggers save
  const setMessages: React.Dispatch<React.SetStateAction<RuntimeMessage[]>> =
    React.useCallback(
      (action) => {
        setMessagesInternal((prev) => {
          const next = typeof action === "function" ? action(prev) : action;
          debouncedSave(next, selectedDocRef.current);
          return next;
        });
      },
      [debouncedSave]
    );

  // Set selected doc and save immediately (no debounce for doc changes)
  const setSelectedDoc = React.useCallback(
    (docId: string) => {
      setSelectedDocInternal(docId);

      // Save immediately when doc changes
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
      pendingStateRef.current = null;
      saveToStorage(messagesRef.current, docId);
    },
    []
  );

  // Clear chat and storage
  const clearChat = React.useCallback(() => {
    // Cancel pending saves
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    pendingStateRef.current = null;

    // Reset state
    setMessagesInternal([]);
    // Keep selectedDoc - don't reset on new chat

    // Clear storage
    clearStorage();
  }, []);

  // Listen for storage changes from other tabs
  React.useEffect(() => {
    if (typeof window === "undefined") return;

    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && e.newValue !== null) {
        // Another tab updated the storage
        console.info("[useChatStorage] Storage updated by another tab");
      }
    };

    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, []);

  return {
    messages,
    setMessages,
    selectedDoc,
    setSelectedDoc,
    clearChat,
    storageAvailable,
    isHydrated,
  };
}
