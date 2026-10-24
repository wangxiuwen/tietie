export type ItemKind = "text" | "link" | "image" | "code" | "color";

export interface ClipItem {
  id: number;
  kind: ItemKind;
  content: string;
  preview: string;
  meta: string;
  pinned: boolean;
  folder_id: number | null;
  source_app: string | null;
  created_at: number;
  used_at: number;
  use_count: number;
  byte_size: number;
  rich_html?: string | null;
}

export interface Folder {
  id: number;
  name: string;
  color: string;
  sort_order: number;
}

export interface Memo {
  id: number;
  kind: ItemKind | string;
  content: string;
  preview: string;
  color: string;
  pinned: boolean;
  sort: number;
  source_item_id: number | null;
  created_at: number;
}

export const KIND_COLOR: Record<ItemKind, string> = {
  text: "var(--cat-text)",
  link: "var(--cat-link)",
  image: "var(--cat-image)",
  code: "var(--cat-code)",
  color: "var(--cat-color)",
};

import { t } from "./i18n";

/** Localized kind label (i18n-aware replacement for the old KIND_LABEL map). */
export function kindLabel(kind: string): string {
  return t("kind." + (kind in KIND_COLOR ? kind : "text"));
}
