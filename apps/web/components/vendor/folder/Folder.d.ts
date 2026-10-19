import type { CSSProperties, ReactElement, ReactNode } from "react";

/** Types for the React Bits Folder component (Folder.jsx, copied in unchanged). */
export type FolderItem =
  | string
  | number
  | ReactElement
  | { title?: string; description?: string }
  | { image: string; title?: string; alt?: string }
  | { content: ReactNode };

export interface FolderProps {
  items?: FolderItem[];
  children?: ReactNode;
  label?: string;
  mode?: "flap" | "book";
  variant?: "solid" | "glass" | "matte";
  layout?: "spread" | "stack" | "row";
  color?: string;
  paperColor?: string;
  tabPosition?: "left" | "center" | "right";
  openOn?: "click" | "hover";
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  onItemClick?: (item: FolderItem, index: number) => void;
  onItemDrop?: (item: FolderItem, index: number, inside: boolean) => void;
  draggable?: boolean;
  zoomOnClick?: boolean;
  peek?: boolean;
  intro?: boolean;
  size?: number;
  frost?: number;
  tilt?: number;
  speed?: number;
  bounce?: number;
  closeOnOutsideClick?: boolean;
  theme?: "dark" | "light";
  className?: string;
  style?: CSSProperties;
}

declare function Folder(props: FolderProps): ReactElement;
export default Folder;
