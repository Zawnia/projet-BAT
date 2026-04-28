import type { ImportedDetectionStore } from "./types";

class ImportedStoreManager {
  private stores = new Map<string, ImportedDetectionStore>();

  add(store: ImportedDetectionStore): void {
    this.stores.set(store.id, {
      ...store,
      metadata: { ...store.metadata },
      rows: store.rows.map((row) => ({ ...row }))
    });
  }

  get(id: string): ImportedDetectionStore | null {
    return this.stores.get(id) ?? null;
  }

  getRange(id: string, start: number, end: number) {
    return this.stores.get(id)?.rows.slice(start, end) ?? [];
  }

  clear(): void {
    this.stores.clear();
  }

  hydrate(stores: ImportedDetectionStore[] | undefined): void {
    this.clear();
    for (const store of stores ?? []) this.add(store);
  }

  toJSON(): ImportedDetectionStore[] {
    return Array.from(this.stores.values()).map((store) => ({
      ...store,
      metadata: { ...store.metadata },
      rows: store.rows.map((row) => ({ ...row }))
    }));
  }

  removeUnused(referencedStoreIds: Iterable<string>): void {
    const referenced = new Set(referencedStoreIds);
    for (const id of this.stores.keys()) {
      if (!referenced.has(id)) this.stores.delete(id);
    }
  }

  list(): { id: string; filename: string; nRows: number }[] {
    return Array.from(this.stores.values()).map((store) => ({
      id: store.id,
      filename: store.filename,
      nRows: store.rows.length
    }));
  }
}

export const importedStoreManager = new ImportedStoreManager();
