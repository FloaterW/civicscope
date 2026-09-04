import { createSocialImage, socialImageSize } from "./social-image";

export const alt = "CivicScope GTA Housing Affordability Explorer";
export const size = socialImageSize;
export const contentType = "image/png";

export default function TwitterImage() {
  return createSocialImage();
}
