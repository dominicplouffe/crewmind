/** Tracks files being sent to the project from the composer. */
import { useCallback, useState } from "react";
import { ApiError } from "../api/client";
import { uploadFile } from "../api/upload";
import { t } from "../strings";

export interface UploadItem {
  key: string;
  name: string;
  progress: number;
  done: boolean;
  error: { message: string; hint: string | null } | null;
}

let counter = 0;

export function useUploads(projectId: string, onStored: () => void): {
  uploads: UploadItem[];
  add(files: File[]): void;
  dismiss(key: string): void;
} {
  const [uploads, setUploads] = useState<UploadItem[]>([]);

  const patch = useCallback((key: string, change: Partial<UploadItem>) => {
    setUploads((items) => items.map((item) => (item.key === key ? { ...item, ...change } : item)));
  }, []);

  const add = useCallback(
    (files: File[]) => {
      for (const file of files) {
        counter += 1;
        const key = `upload-${counter}`;
        const named = file.name ? file : new File([file], t.composer.pastedName(counter), { type: file.type });
        setUploads((items) => [...items, { key, name: named.name, progress: 0, done: false, error: null }]);
        uploadFile(projectId, named, (progress) => patch(key, { progress }))
          .then(() => {
            patch(key, { done: true, progress: 1 });
            onStored();
          })
          .catch((error: unknown) => {
            const api = error instanceof ApiError ? error : null;
            patch(key, {
              error: { message: api?.message ?? t.errors.network, hint: api ? api.hint : t.errors.networkHint },
            });
          });
      }
    },
    [onStored, patch, projectId],
  );

  const dismiss = useCallback((key: string) => {
    setUploads((items) => items.filter((item) => item.key !== key));
  }, []);

  return { uploads, add, dismiss };
}
