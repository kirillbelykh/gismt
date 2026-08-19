"""CryptoPro wrapper for digital signatures"""
import tempfile
import os
import shutil
import base64
import subprocess
import sys
import platform
from typing import Optional
from config import settings
from logger import get_logger



logger = get_logger(__name__)

# Windows-specific imports (only if on Windows to avoid import errors on macOS)
if platform.system() == "Windows":
    try:
        import pythoncom
        import win32com.client
        from win32com.client import Dispatch
        WINDOWS_COM_AVAILABLE = True
    except ImportError:
        WINDOWS_COM_AVAILABLE = False
        logger.warning("pywin32 not available on Windows, falling back to mock mode")
else:
    WINDOWS_COM_AVAILABLE = False

# Windows constants
if platform.system() == "Windows":
    CADES_BES = 1
    CADESCOM_BASE64_TO_BINARY = 1
    CAPICOM_ENCODE_BASE64 = 0
    CAPICOM_AUTHENTICATED_ATTRIBUTE_SIGNING_TIME = 0
    CAPICOM_CURRENT_USER_STORE = 2
    CAPICOM_MY_STORE = "My"
    CAPICOM_STORE_OPEN_MAXIMUM_ALLOWED = 2


class CryptoProSigner:
    """Wrapper for CryptoPro CSP with cross-platform support"""

    def __init__(self, thumbprint: Optional[str] = None):
        """
        Initialize CryptoPro signer

        Args:
            thumbprint: Certificate thumbprint. If None, uses CRPT_THUMBPRINT from settings
        """
        self.thumbprint = thumbprint or settings.CRPT_THUMBPRINT
        self.os_type = platform.system()

        # Initialize platform-specific components
        if self.os_type == "Darwin":  # macOS
            self.cryptcp_path = self._find_cryptcp()
            self._is_macos = True
        elif self.os_type == "Windows":
            self._is_macos = False
            if not WINDOWS_COM_AVAILABLE and not settings.CRPT_MOCK_MODE:
                raise ImportError(
                    "pywin32 is not available. Please install it with 'pip install pywin32' "
                    "or enable CRPT_MOCK_MODE in settings."
                )
        else:
            logger.warning(f"Unsupported OS: {self.os_type}. Using mock mode.")
            self._is_macos = False  # Treat as Windows-like for mock mode

    def _find_cryptcp(self) -> str:
        """Find cryptcp executable path (macOS/Linux only)"""
        possible_paths = [
            '/opt/cprocsp/bin/cryptcp',  # macOS/Linux
            '/opt/cprocsp/bin/amd64/cryptcp',  # Linux 64-bit
            'cryptcp',  # In PATH
        ]

        for path in possible_paths:
            if path == 'cryptcp':
                # Check if in PATH
                result = subprocess.run(['which', 'cryptcp'], capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout.strip()
            elif os.path.exists(path):
                return path

        # If not found and in mock mode, return dummy path
        if settings.CRPT_MOCK_MODE:
            logger.warning("cryptcp not found, but MOCK_MODE is enabled")
            return '/usr/bin/echo'  # Dummy command

        raise FileNotFoundError(
            f"cryptcp not found. Please install CryptoPro CSP or enable MOCK_MODE. "
            f"Tried paths: {possible_paths}"
        )

    def _windows_find_certificate(self):
        """Find certificate by thumbprint on Windows"""
        pythoncom.CoInitialize()
        try:
            store = win32com.client.Dispatch("CAdESCOM.Store")
            store.Open(
                CAPICOM_CURRENT_USER_STORE,
                CAPICOM_MY_STORE,
                CAPICOM_STORE_OPEN_MAXIMUM_ALLOWED
            )

            found = None
            for cert in store.Certificates:
                try:
                    cert_thumbprint = getattr(cert, "Thumbprint", "")
                    if cert_thumbprint.lower() == self.thumbprint.lower():
                        found = cert
                        break
                except Exception:
                    continue

            if found is None:
                raise Exception(f"Certificate with thumbprint {self.thumbprint} not found")

            return found
        finally:
            store.Close()
            pythoncom.CoUninitialize()

    def _windows_sign_data(self, cert, data_str: str, detached: bool = False) -> str:
        """Sign data using Windows CryptoPro"""
        pythoncom.CoInitialize()
        try:
            # Convert string to base64 for Windows CryptoPro
            base64_content = base64.b64encode(data_str.encode('utf-8')).decode('ascii')

            signer = Dispatch("CAdESCOM.CPSigner")
            signer.Certificate = cert

            # Add signing time attribute
            oSigningTimeAttr = Dispatch("CAdESCOM.CPAttribute")
            oSigningTimeAttr.Name = CAPICOM_AUTHENTICATED_ATTRIBUTE_SIGNING_TIME
            import datetime
            oSigningTimeAttr.Value = datetime.datetime.now()
            signer.AuthenticatedAttributes2.Add(oSigningTimeAttr)

            # Create and sign data
            signed_data = Dispatch("CAdESCOM.CadesSignedData")
            signed_data.ContentEncoding = CADESCOM_BASE64_TO_BINARY
            signed_data.Content = base64_content

            # Sign with CAdES-BES format
            signature = signed_data.SignCades(
                signer,
                CADES_BES,
                detached,
                CAPICOM_ENCODE_BASE64
            )

            if isinstance(signature, bytes):
                signature = signature.decode("ascii", errors="ignore")

            # Clean up signature string
            return signature.replace("\r", "").replace("\n", "")
        finally:
            pythoncom.CoUninitialize()

    def _macos_sign_data(self, data_str: str, detached: bool = False, cadesbes: bool = False) -> str:
        """Sign data using macOS/Linux cryptcp"""
        temp_dir = tempfile.mkdtemp()
        original_cwd = os.getcwd()

        try:
            os.chdir(temp_dir)

            input_file = "data_to_sign.txt"
            output_file = "signature.p7s"

            with open(input_file, 'w', encoding='utf-8') as f:
                f.write(data_str)

            # Build command
            cmd = [self.cryptcp_path, '-sign', '-der']

            if cadesbes:
                cmd.append('-cadesbes')
            if detached:
                cmd.append('-detached')

            cmd.extend(['-thumbprint', self.thumbprint, input_file, output_file])

            # Execute command
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                error_msg = (
                    f"CryptoPro signing failed: {result.stderr.strip()}\n"
                    f"Command: {' '.join(cmd)}\n"
                    f"Return code: {result.returncode}"
                )
                logger.error(error_msg)
                raise Exception(error_msg)

            # Read signature
            with open(output_file, 'rb') as f:
                signature_der = f.read()

            signature_b64 = base64.b64encode(signature_der).decode('ascii')
            return signature_b64.replace("\r\n", "").replace("\n", "").replace("\r", "")

        finally:
            os.chdir(original_cwd)
            shutil.rmtree(temp_dir, ignore_errors=True)

    def sign_data(
        self,
        data_str: str,
        detached: bool = False,
        cadesbes: bool = False
    ) -> str:
        """
        Sign data using CryptoPro CSP (cross-platform)

        Args:
            data_str: Data string to sign (UTF-8)
            detached: True for detached signature (required for SUZ)
            cadesbes: True for CAdES-BES format (required for GIS MT)

        Returns:
            Base64-encoded signature without line breaks

        Raises:
            Exception: If signing fails
        """

        # Platform-specific signing
        if self._is_macos:
            # macOS/Linux path
            return self._macos_sign_data(data_str, detached, cadesbes)
        else:
            # Windows path
            if self.os_type == "Windows" and WINDOWS_COM_AVAILABLE:
                # On Windows, cadesbes is always True (CAdES-BES format)
                if not cadesbes:
                    logger.warning("Windows CryptoPro always uses CAdES-BES format")

                # Find certificate and sign
                cert = self._windows_find_certificate()
                return self._windows_sign_data(cert, data_str, detached)
            else:
                # Fallback for unsupported OS or missing pywin32 in mock mode
                if settings.CRPT_MOCK_MODE:
                    mock_sig = base64.b64encode(f"MOCK_SIGNATURE_{self.thumbprint[:8]}".encode()).decode()
                    logger.info("Using mock signature (unsupported OS or missing pywin32)")
                    return mock_sig
                else:
                    raise EnvironmentError(
                        f"CryptoPro not properly configured for {self.os_type}. "
                        f"For Windows, install pywin32. For macOS, install CryptoPro CSP."
                    )