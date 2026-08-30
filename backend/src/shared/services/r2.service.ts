import {
  DeleteObjectCommand,
  GetObjectCommand,
  S3Client,
  PutObjectCommand,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import crypto from "crypto";
import logger from "../../utils/logger";

const credentials = {
  accessKeyId: process.env.R2_ACCESS_KEY_ID!,
  secretAccessKey: process.env.R2_SECRET_ACCESS_KEY!,
};

const r2Client = new S3Client({
  region: "us-east-1",
  endpoint: process.env.R2_ENDPOINT!,
  credentials,
  forcePathStyle: true,
});

/**
 * Separate client used only to sign URLs.
 *
 * A signature covers the host, so a URL signed against `R2_ENDPOINT` is only
 * valid at that host — fine for Cloudflare R2, whose S3 endpoint is publicly
 * reachable, but useless when the bucket is reached over a private network
 * (a self-hosted MinIO on `http://minio:9000`, say). `R2_PUBLIC_ENDPOINT` lets
 * such a deployment sign against the host the browser actually talks to, and
 * falls back to `R2_ENDPOINT` so existing setups keep working untouched.
 */
const signingClient = process.env.R2_PUBLIC_ENDPOINT
  ? new S3Client({
      region: "us-east-1",
      endpoint: process.env.R2_PUBLIC_ENDPOINT,
      credentials,
      forcePathStyle: true,
    })
  : r2Client;

/** How long a signed resume link stays valid. */
const SIGNED_URL_TTL_SECONDS = Number(
  process.env.SIGNED_URL_TTL_SECONDS ?? 900,
);

// Server-controlled extension per content type. We never trust the client
// filename for the stored key (an attacker could upload a `.html`/`.svg`).
const EXT_BY_MIME: Record<string, string> = {
  "application/pdf": ".pdf",
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/webp": ".webp",
  "image/svg+xml": ".svg",
};

export const r2Service = {
  async uploadFile(
    file: Express.Multer.File,
    folder: "resumes" | "logos" = "resumes",
  ): Promise<string> {
    const fileExt = EXT_BY_MIME[file.mimetype] ?? "";
    const fileName = `${folder}/${crypto.randomUUID()}${fileExt}`;

    // Logos are raster images (png/jpeg/webp — never svg) meant to render
    // inline in the UI. Everything else (resumes, and any svg) is forced to
    // download so an uploaded file can never execute as HTML/SVG when its
    // URL is opened directly in a browser.
    const isInlineableLogo =
      folder === "logos" &&
      ["image/png", "image/jpeg", "image/webp"].includes(file.mimetype);

    const command = new PutObjectCommand({
      Bucket: process.env.R2_BUCKET_NAME!,
      Key: fileName,
      Body: file.buffer,
      ContentType: file.mimetype,
      ContentDisposition: isInlineableLogo ? "inline" : "attachment",
    });

    try {
      await r2Client.send(command);
    } catch (error) {
      logger.error(
        `Attempting upload to Bucket: ${process.env.R2_BUCKET_NAME}`,
      );
      throw error;
    }

    const publicUrl = process.env.R2_PUBLIC_URL?.endsWith("/")
      ? process.env.R2_PUBLIC_URL.slice(0, -1)
      : process.env.R2_PUBLIC_URL;

    return `${publicUrl}/${fileName}`;
  },

  extractKeyFromUrl(fileUrl: string): string | null {
    if (!fileUrl) return null;

    const base = process.env.R2_PUBLIC_URL?.endsWith("/")
      ? process.env.R2_PUBLIC_URL.slice(0, -1)
      : process.env.R2_PUBLIC_URL;

    if (!base) return null;
    if (!fileUrl.startsWith(`${base}/`)) return null;

    return fileUrl.replace(`${base}/`, "");
  },

  /**
   * Turns a stored file URL into a short-lived signed one.
   *
   * Resumes are personal data, so `resumes/` is not anonymously readable and a
   * stored URL alone opens nothing. Callers hand the signed URL to an already
   * authorised viewer; it expires on its own, which a permanent public link
   * never does.
   *
   * Returns the URL unchanged when it points outside our bucket, and null for
   * null input, so callers can map over optional values without branching.
   */
  async signUrl(fileUrl: string | null): Promise<string | null> {
    if (!fileUrl) return null;

    const key = this.extractKeyFromUrl(fileUrl);
    if (!key) return fileUrl;

    try {
      return await getSignedUrl(
        signingClient,
        new GetObjectCommand({
          Bucket: process.env.R2_BUCKET_NAME!,
          Key: key,
        }),
        { expiresIn: SIGNED_URL_TTL_SECONDS },
      );
    } catch (error) {
      // A viewer seeing no resume is better than a 500 on the whole record.
      logger.error(`Failed to sign URL for key ${key}: ${error}`);
      return null;
    }
  },

  async deleteByUrl(fileUrl: string): Promise<void> {
    const key = this.extractKeyFromUrl(fileUrl);
    if (!key) return;

    const command = new DeleteObjectCommand({
      Bucket: process.env.R2_BUCKET_NAME!,
      Key: key,
    });

    await r2Client.send(command);
  },
};
