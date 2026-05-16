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
}

export interface Folder {
  id: number;
  name: string;
  color: string;
  sort_order: number;
}

export const KIND_LABEL: Record<ItemKind, string> = {
  text: "文本",
  link: "链接",
  image: "图片",
  code: "代码",
  color: "颜色",
};

export const KIND_COLOR: Record<ItemKind, string> = {
  text: "var(--cat-text)",
  link: "var(--cat-link)",
  image: "var(--cat-image)",
  code: "var(--cat-code)",
  color: "var(--cat-color)",
};
