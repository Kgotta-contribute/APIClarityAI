 

"""

Encryption service for file encryption using DEK (Data Encryption Key) and KEK (Key Encryption Key).

 

This service implements a two-tier encryption approach:

1. File content is encrypted with a randomly generated DEK using AES-256-CBC

2. The DEK is encrypted using Protegrity API (acting as KEK)

3. The encrypted DEK and IV are prepended to the encrypted file content

 

File format: [4 bytes: encrypted_dek_length] + [encrypted_dek] + [16 bytes: IV] + [encrypted_content]

"""

 

import traceback

import os

import logging

import base64

import requests

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import re

from app.config.config import settings

 

logger = logging.getLogger(__name__)

 

class EncryptionService:

    """Service for encrypting and decrypting files using DEK/KEK pattern with Protegrity."""

   

    def __init__(self):

        """Initialize the encryption service with Protegrity configuration."""

        self.protegrity_url = settings.protegrity_url

        self.protect_path = "/protect"

        self.unprotect_path = "/unprotect"

        self.verify_ssl = False

       

        # Suppress SSL warnings if verification is disabled

        if not self.verify_ssl:

            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

       

        logger.info("Initialized EncryptionService with Protegrity integration")

   

    def _encrypt_dek_with_protegrity(self, dek: bytes) -> bytes:

        """

        Encrypt the DEK using Protegrity API (KEK).

       

        Args:

            dek: The Data Encryption Key to encrypt

           

        Returns:

            bytes: Encrypted DEK

           

        Raises:

            Exception: If Protegrity API call fails

        """

        url = f"{self.protegrity_url}{self.protect_path}"

       

        # Prepare the request payload

        payload = {

            "de_element": "AES256",

            "sensitive_info": dek.decode()  # Convert bytes to base64 string

        }

       

        headers = {

            'Content-Type': 'application/json'

        }

       

        try:            

            response = requests.post(

                url,

                json=payload,

                headers=headers,

                verify=self.verify_ssl,

                timeout=30

            )

           

            if response.status_code != 200:

                error_msg = f"Protegrity encryption failed with status {response.status_code}: {response.text}"

                logger.error(error_msg)

   

                raise Exception(error_msg)

           

            # The response should contain the encrypted DEK

            # Protegrity returns a JSON string (base64 encoded)

            masked_value = response.json()  # This returns a base64 string

            logger.info(f"Protegrity encrypt response type: {type(masked_value)}")

            logger.info(f"Protegrity encrypt response (first 100 chars): {str(masked_value)[:100]}...")

           

            # Store the base64 string as bytes

           

            logger.info(f"DEK encrypted successfully, encrypted DEK length: {len(masked_value)} bytes")

           

            return masked_value

           

        except requests.exceptions.RequestException as e:

            logger.error(f"Error calling Protegrity API for encryption: {str(e)}", exc_info=True)

            # Add structured logging for Splunk monitoring

 

            raise Exception(f"Failed to encrypt DEK with Protegrity: {str(e)}")

   

    def _decrypt_dek_with_protegrity(self, encrypted_dek: bytes) -> bytes:

        """

        Decrypt the DEK using Protegrity API (KEK).

       

        Args:

            encrypted_dek: The encrypted Data Encryption Key

           

        Returns:

            bytes: Decrypted DEK

           

        Raises:

            Exception: If Protegrity API call fails

        """

        url = f"{self.protegrity_url}{self.unprotect_path}"

       

        # Prepare the request payload

        payload = {

            "de_element": "AES256",

            "sensitive_info": encrypted_dek

        }

       

        headers = {

            'Content-Type': 'application/json'

        }

       

        try:            

            response = requests.post(

                url,

                json=payload,

                headers=headers,

                verify=self.verify_ssl,

                timeout=30

            )

           

            if response.status_code != 200:

                error_msg = f"Protegrity decryption failed with status {response.status_code}: {response.text}"

                logger.error(error_msg)

   

                raise Exception(error_msg)

           

            # The response should contain the decrypted DEK as base64 string

            # Protegrity returns the original base64 string that was sent during encryption

            unmasked_value = response.json()  # This returns the base64 string

            logger.info(f"Protegrity decrypt response type: {type(unmasked_value)}")

           

            # Convert base64 string to bytes

            try:

                decrypted_dek = base64.b64decode(unmasked_value)

                logger.info(f"DEK decrypted successfully, DEK length: {len(decrypted_dek)} bytes")

            except Exception as e:

                logger.error(f"Invalid base64 string from Protegrity - Response type: {type(unmasked_value)}, Error: {str(e)}", exc_info=True)

                logger.error(f"Response content: {str(unmasked_value)[:200]}")

                logger.error(f"Expected base64 string but got: {repr(unmasked_value[:50])}")

   

                raise Exception(f"Protegrity returned invalid base64 string: {str(e)}")

           

            logger.debug(f"DEK decrypted successfully, DEK length: {len(decrypted_dek)}")

           

            return decrypted_dek

           

        except requests.exceptions.RequestException as e:

            logger.error(f"Error calling Protegrity API for decryption: {str(e)}", exc_info=True)

 

            raise Exception(f"Failed to decrypt DEK with Protegrity: {str(e)}")

   

    def encrypt_file_content(self, file_content: bytes) -> bytes:

        """

        Encrypt file content using DEK/KEK pattern (legacy method with embedded metadata).

       

        Process:

        1. Generate random DEK (32 bytes for AES-256) and IV (16 bytes)

        2. Encrypt file content with AES-256-CTR using DEK

        3. Encrypt DEK using Protegrity API (KEK)

        4. Prepend encrypted DEK length, encrypted DEK, and IV to encrypted content

       

        Args:

            file_content: The file content to encrypt

           

        Returns:

            bytes: Encrypted file with prepended encrypted DEK and IV

            Format: [4 bytes: encrypted_dek_length] + [encrypted_dek] + [16 bytes: IV] + [encrypted_content]

           

        Raises:

            Exception: If encryption fails

        """

        try:

            logger.info(f"Starting file encryption, file size: {len(file_content)} bytes")

           

            # Step 1: Generate random DEK and IV

            dek = os.urandom(32)  # 256 bits for AES-256

            iv = os.urandom(16)   # 128 bits for AES block size

            logger.debug(f"Generated DEK (32 bytes) and IV (16 bytes)")

           

            encoded_key = base64.b64encode(dek)

            encoded_iv = base64.b64encode(iv)

 

            encrypted_dek = self._encrypt_dek_with_protegrity(encoded_key)

            # Encrypt with AES-256-CTR

            cipher = Cipher(algorithm=algorithms.AES(dek), mode=modes.CTR(iv))

            encryptor = cipher.encryptor()

 

            meta = "[ProtectedDek = %s; IV = %s]" % (encrypted_dek, encoded_iv.decode())

            meta_len_b = len(meta).to_bytes(4, 'big')

            encrypted_file_content = meta_len_b + meta.encode() + encryptor.update(file_content) + encryptor.finalize()

 

            logger.debug(f"File content encrypted, encrypted size: {len(encrypted_file_content)} bytes")

           

           

            logger.info(f"File encryption completed successfully, total size: {len(encrypted_file_content)} bytes")

            logger.debug(f"Structure: encrypted_dek_length={len(encrypted_dek)}, iv=16 bytes, encrypted_content={len(file_content)} bytes")

           

            return encrypted_file_content

           

        except Exception as e:

            logger.error(f"File encryption failed: {str(e)}", exc_info=True)

            raise Exception(f"Failed to encrypt file: {str(e)}")

   

    def encrypt_file_with_metadata(self, file_content: bytes) -> tuple:

        """

        Encrypt file content and return encrypted content with metadata separately.

        This method is designed for storing encryption metadata in MongoDB.

       

        Process:

        1. Generate random DEK (32 bytes for AES-256) and IV (16 bytes)

        2. Encrypt file content with AES-256-CTR using DEK

        3. Encrypt DEK using Protegrity API (KEK)

        4. Return encrypted content and metadata separately

       

        Args:

            file_content: The file content to encrypt

           

        Returns:

            tuple: (encrypted_content: bytes, metadata: dict)

                   metadata contains: {"encryptedDEK": str, "iv": str}

           

        Raises:

            Exception: If encryption fails

        """

        try:

            logger.info(f"Starting file encryption with separate metadata, file size: {len(file_content)} bytes")

           

            # Generate random DEK and IV

            dek = os.urandom(32)  # 256 bits for AES-256

            iv = os.urandom(16)   # 128 bits for AES block size

            logger.debug(f"Generated DEK (32 bytes) and IV (16 bytes)")

           

            encoded_key = base64.b64encode(dek)

            encoded_iv = base64.b64encode(iv)

 

            # Encrypt DEK with Protegrity

            encrypted_dek = self._encrypt_dek_with_protegrity(encoded_key)

           

            # Encrypt file content with AES-256-CTR

            cipher = Cipher(algorithm=algorithms.AES(dek), mode=modes.CTR(iv))

            encryptor = cipher.encryptor()

            encrypted_content = encryptor.update(file_content) + encryptor.finalize()

 

            logger.debug(f"File content encrypted, encrypted size: {len(encrypted_content)} bytes")

           

            # Prepare metadata dictionary

            metadata = {

                "encryptedDEK": encrypted_dek,

                "iv": encoded_iv.decode()

            }

           

            logger.info(f"File encryption completed successfully, encrypted size: {len(encrypted_content)} bytes")

           

            return encrypted_content, metadata

           

        except Exception as e:

            logger.error(f"File encryption with metadata failed: {str(e)}", exc_info=True)

 

            raise Exception(f"Failed to encrypt file: {str(e)}")

   

    def decrypt_file_content(self, encrypted_content: bytes) -> bytes:

        """

        Decrypt file content that was encrypted using encrypt_file() (legacy method).

       

        Process:

        1. Extract encrypted DEK length, encrypted DEK, and IV from prepended data

        2. Decrypt DEK using Protegrity API (KEK)

        3. Decrypt file content with AES-256-CTR using decrypted DEK and IV

       

        Args:

            encrypted_content: The encrypted file content with prepended encrypted DEK and IV

            Format: [4 bytes: encrypted_dek_length] + [encrypted_dek] + [16 bytes: IV] + [encrypted_content]

           

        Returns:

            bytes: Decrypted file content

           

        Raises:

            Exception: If decryption fails

        """

        try:

            logger.debug(f"Starting legacy decryption, file size: {len(encrypted_content)} bytes")

            logger.debug(f"First 20 bytes: {encrypted_content[:20]}")

           

            b = encrypted_content[:4]

            meta_len = int.from_bytes(b, 'big')

            logger.debug(f"Metadata length: {meta_len}")

           

            if meta_len > len(encrypted_content) or meta_len <= 0:

   

                raise Exception(f"Invalid metadata length: {meta_len}, file size: {len(encrypted_content)}")

           

            meta = encrypted_content[4:4+meta_len]

            logger.debug(f"Metadata bytes (first 100): {meta[:100]}")

           

            try:

                meta_str = meta.decode('utf-8')

                logger.debug(f"Metadata string: {meta_str[:200]}")

            except UnicodeDecodeError as decode_err:

                logger.error(f"Failed to decode metadata as UTF-8 - FileID: {file_id}, Error: {decode_err}", exc_info=True)

                logger.error(f"Metadata appears to be binary, not text. File may not be in legacy format.")

   

                raise Exception(f"File does not appear to be in legacy encrypted format (metadata is not UTF-8 text)")

           

            groups = re.search(r"\[ProtectedDek = (.*); IV = (.*?)\]", meta_str).groups()

            key = groups[0]

            iv = base64.b64decode(groups[1])

   

            dek = self._decrypt_dek_with_protegrity(key)

            cipher = Cipher(algorithm=algorithms.AES(dek), mode=modes.CTR(iv))

            decryptor = cipher.decryptor()

            file_content = decryptor.update(encrypted_content[4+meta_len:]) + decryptor.finalize()

 

            return file_content

           

        except Exception as e:

            logger.error(f"File decryption failed: {str(e)}", exc_info=True)

 

            raise Exception(f"Failed to decrypt file: {str(e)}")

   

    def decrypt_file_with_metadata(self, encrypted_content: bytes, metadata: dict) -> bytes:

        """

        Decrypt file content using metadata stored separately (e.g., in MongoDB).

       

        Process:

        1. Extract encrypted DEK and IV from metadata

        2. Decrypt DEK using Protegrity API (KEK)

        3. Decrypt file content with AES-256-CTR using decrypted DEK and IV

       

        Args:

            encrypted_content: The encrypted file content (no header)

            metadata: Dictionary containing {"encryptedDEK": str, "iv": str}

           

        Returns:

            bytes: Decrypted file content

           

        Raises:

            Exception: If decryption fails or metadata is invalid

        """

        try:

            if not metadata or "encryptedDEK" not in metadata or "iv" not in metadata:

   

                raise Exception("Invalid metadata: missing encryptedDEK or iv")

           

            encrypted_dek = metadata["encryptedDEK"]

            iv = base64.b64decode(metadata["iv"])

           

            logger.debug(f"Decrypting file with metadata, encrypted size: {len(encrypted_content)} bytes")

           

            # Decrypt DEK using Protegrity

            dek = self._decrypt_dek_with_protegrity(encrypted_dek)

           

            # Decrypt file content with AES-256-CTR

            cipher = Cipher(algorithm=algorithms.AES(dek), mode=modes.CTR(iv))

            decryptor = cipher.decryptor()

            file_content = decryptor.update(encrypted_content) + decryptor.finalize()

           

            logger.info(f"File decrypted successfully, decrypted size: {len(file_content)} bytes")

           

            return file_content

           

        except Exception as e:

            logger.error(f"File decryption with metadata failed: {str(e)}", exc_info=True)

 

            raise Exception(f"Failed to decrypt file: {str(e)}")

   

    def decrypt_chunk_with_offset(self, encrypted_chunk: bytes, metadata: dict, offset: int) -> bytes:

        """

        Decrypt a chunk of encrypted content starting at a specific byte offset.

        This enables HTTP Range requests for streaming encrypted files.

       

        AES-CTR mode allows decryption at any offset by adjusting the counter value.

       

        Args:

            encrypted_chunk: The encrypted chunk to decrypt

            metadata: Dictionary containing {"encryptedDEK": str, "iv": str}

            offset: Byte offset in the original encrypted file where this chunk starts

           

        Returns:

            bytes: Decrypted chunk

           

        Raises:

            Exception: If decryption fails or metadata is invalid

        """

        try:

            if not metadata or "encryptedDEK" not in metadata or "iv" not in metadata:

   

                raise Exception("Invalid metadata: missing encryptedDEK or iv")

           

            encrypted_dek = metadata["encryptedDEK"]

            iv = base64.b64decode(metadata["iv"])

           

            logger.debug(f"Decrypting chunk at offset {offset}, chunk size: {len(encrypted_chunk)} bytes")

           

            # Decrypt DEK using Protegrity

            dek = self._decrypt_dek_with_protegrity(encrypted_dek)

           

            # Calculate counter value for the offset

            # AES block size is 16 bytes

            block_offset = offset // 16

            byte_offset = offset % 16

           

            # Adjust IV for CTR mode offset

            # CTR mode uses IV as initial counter value

            counter = int.from_bytes(iv, 'big') + block_offset

            adjusted_iv = counter.to_bytes(16, 'big')

           

            # Decrypt the chunk

            cipher = Cipher(algorithm=algorithms.AES(dek), mode=modes.CTR(adjusted_iv))

            decryptor = cipher.decryptor()

            decrypted = decryptor.update(encrypted_chunk) + decryptor.finalize()

           

            # If offset is not block-aligned, skip the first few bytes

            if byte_offset > 0:

                decrypted = decrypted[byte_offset:]

           

            logger.debug(f"Chunk decrypted successfully, decrypted size: {len(decrypted)} bytes")

           

            return decrypted

           

        except Exception as e:

            logger.error(f"Chunk decryption with offset failed: {str(e)}", exc_info=True)

 

            raise Exception(f"Failed to decrypt chunk: {str(e)}")

 

# Singleton instance

encryption_service = EncryptionService()