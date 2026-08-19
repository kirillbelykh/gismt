"""Unified CRPT client for SUZ and TRUE API"""
import json
import os
import time
import base64
import asyncio
from typing import Optional, Dict, Any, List, Tuple
import httpx
from app.core.config import settings
from app.services.signer_service import CryptoProSigner
from app.core.logging import get_logger
from app.services.code_parse_service import extract_sntin

logger = get_logger(__name__)


class CRPTClient:
    """Unified client for CRPT SUZ and TRUE API"""

    def __init__(
        self,
        thumbprint: Optional[str] = None,
        oms_id: Optional[str] = None,
        oms_conn_id: Optional[str] = None,
    ):
        """
        Initialize CRPT client

        Args:
            thumbprint: Certificate thumbprint
            oms_id: OMS ID
            oms_conn_id: OMS connection ID
        """
        self.thumbprint = thumbprint or settings.CRPT_THUMBPRINT
        self.oms_id = oms_id or settings.OMS_ID
        self.oms_conn_id = oms_conn_id or settings.OMS_CONN_ID
        self.signer = CryptoProSigner(self.thumbprint)
        # Separate tokens for SUZ and TRUE API
        self._suz_token: Optional[str] = None
        self._suz_token_created_at: Optional[float] = None
        self._true_api_token: Optional[str] = None
        self._true_api_token_created_at: Optional[float] = None
        self._token_ttl = 9 * 3600  # 9 hours
        self.TOKEN_PATH = os.path.join(os.path.dirname(__file__), "token.json")
        self.TOKEN_TTL = 9 * 3600  # 9 часов

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get HTTP client with timeout"""
        return httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            verify=True,  # Verify SSL certificates
        )

    async def get_suz_token(self, force_refresh: bool = False) -> str:
        # 1. Попробовать использовать кэш в памяти
        if not force_refresh and self._suz_token and self._suz_token_created_at:
            if time.time() - self._suz_token_created_at < self.TOKEN_TTL:
                return self._suz_token

        # 2. Попробовать загрузить с диска
        if not force_refresh and os.path.exists(self.TOKEN_PATH):
            try:
                with open(self.TOKEN_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                token = data.get("token")
                created_at = data.get("created_at")
                if token and created_at and (time.time() - created_at < self.TOKEN_TTL):
                    self._suz_token = token
                    self._suz_token_created_at = created_at
                    return token
            except Exception:
                pass

        # 3. Генерация нового токена
        async with await self._get_http_client() as client:
            # Получаем uuid и data для подписи
            url = f"{settings.crpt_auth_url}/auth/key"
            res = await client.get(url, timeout=10.0)
            res.raise_for_status()
            data_json = res.json()
            uuid = data_json['uuid']
            data_to_sign = data_json['data']

            # Подпись через signer
            signature = await self.signer.sign_data(data_to_sign)
            signature = signature.replace("\r", "").replace("\n", "")

            # Запрос на получение токена
            url = f"{settings.crpt_auth_url}/auth/simpleSignIn/{self.oms_conn_id}"
            payload = {"uuid": uuid, "data": signature}
            headers = {"accept": "application/json", "Content-Type": "application/json"}
            res2 = await client.post(url, json=payload, headers=headers, timeout=10.0)
            res2.raise_for_status()
            token = res2.json()['token']

            # Кэш в памяти и на диск
            self._suz_token = token
            self._suz_token_created_at = time.time()
            with open(self.TOKEN_PATH, "w", encoding="utf-8") as f:
                json.dump({"token": token, "created_at": self._suz_token_created_at}, f)

            return token

    async def get_true_api_token(self, force_refresh: bool = False) -> str:
        """
        Get TRUE API authentication token (for introduction/turnover)

        Args:
            force_refresh: Force token refresh

        Returns:
            TRUE API authentication token
        """
        # Check cached token
        if not force_refresh and self._true_api_token and self._true_api_token_created_at:
            elapsed = time.time() - self._true_api_token_created_at
            if elapsed < self._token_ttl:
                return self._true_api_token

        # Generate new TRUE API token
        async with await self._get_http_client() as client:
            # Get random data from TRUE API
            url = f"{settings.crpt_auth_url}/auth/key"
            try:
                logger.debug(f"Requesting auth key from: {url}")
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                uuid = data['uuid']
                data_to_sign = data['data']
                logger.debug(f"Auth key received, UUID: {uuid[:20]}...")
            except httpx.ConnectError as e:
                error_msg = (
                    f"Не удалось подключиться к CRPT API: {url}\n"
                    f"Проверьте интернет-соединение и доступность сервера.\n"
                    f"Ошибка: {e}"
                )
                logger.error(error_msg)
                raise Exception(error_msg)
            except httpx.HTTPError as e:
                error_msg = f"Ошибка HTTP при получении auth key: {e}"
                if hasattr(e, 'response') and e.response is not None:
                    error_msg += f"\nСтатус: {e.response.status_code}\nОтвет: {e.response.text[:200]}"
                logger.error(error_msg)
                raise Exception(error_msg)
            except Exception as e:
                error_msg = f"Неожиданная ошибка при получении auth key: {e}"
                logger.error(error_msg)
                raise Exception(error_msg)

            # Sign data (without detached for auth)
            signature = await self.signer.sign_data(data_to_sign)
            signature = signature.replace("\r", "").replace("\n", "")

            # Get TRUE API token (WITHOUT OMS_CONN_ID in path)
            url = f"{settings.crpt_auth_url}/auth/simpleSignIn"
            headers = {
                "accept": "application/json",
                "Content-Type": "application/json"
            }
            payload = {
                "uuid": uuid,
                "data": signature
            }

            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                token = result['token']

                self._true_api_token = token
                self._true_api_token_created_at = time.time()
                logger.info("TRUE API token obtained successfully")
                return token
            except httpx.HTTPError as e:
                logger.error(f"Failed to get TRUE API token: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Response: {e.response.text}")
                raise Exception(f"TRUE API token request failed: {e}")

    async def get_token(self, force_refresh: bool = False) -> str:
        """
        Get SUZ token (backward compatibility)

        Args:
            force_refresh: Force token refresh

        Returns:
            SUZ authentication token
        """
        return await self.get_suz_token(force_refresh)

    def _canonicalize_json(self, payload: Dict[str, Any]) -> str:
        """Canonicalize JSON for signing"""
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(',', ':'),
            sort_keys=True
        ).replace('\r', '').replace('\n', '')

    async def create_emission_order(
        self,
        product_group: str,
        products: List[Dict[str, Any]],
        attributes: Dict[str, Any],
    ) -> str:
        """
        Create emission order in SUZ

        Args:
            product_group: Product group (e.g., "wheelchairs")
            products: List of product definitions
            attributes: Order attributes

        Returns:
            Order ID
        """
        token = await self.get_suz_token()

        url = f"{settings.crpt_base_url}/api/v3/order?omsId={self.oms_id}"

        payload = {
            "productGroup": product_group,
            "products": products,
            "attributes": attributes
        }

        payload_str = self._canonicalize_json(payload)
        signature = await self.signer.sign_data(payload_str, detached=True)
        signature = signature.replace('\r', '').replace('\n', '')

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "clientToken": token,
            "X-Signature": signature
        }

        async with await self._get_http_client() as client:
            try:
                logger.info(f"Creating emission order at URL: {url}")
                logger.info(f"Payload: {payload_str[:200]}...")  # Log first 200 chars
                logger.info(f"Token length: {len(token)}")

                response = await client.post(url, headers=headers, content=payload_str)

                logger.info(f"Response status: {response.status_code}")
                logger.info(f"Response headers: {dict(response.headers)}")

                response.raise_for_status()
                result = response.json()
                order_id = result['orderId']
                logger.info(f"✅ Emission order created successfully: {order_id}")
                return order_id
            except httpx.HTTPStatusError as e:
                error_detail = f"Response: {e.response.text[:500]}"
                logger.error(f"❌ Failed to create emission order: {e}")
                logger.error(f"URL: {url}")
                logger.error(f"Error detail: {error_detail}")
                raise Exception(f"Emission order creation failed: {e}")
            except httpx.HTTPError as e:
                logger.error(f"❌ Failed to create emission order: {e}")
                logger.error(f"URL: {url}")
                raise Exception(f"Emission order creation failed: {e}")

    async def get_emission_status(self, order_id: str) -> Tuple[int, Optional[str]]:
        """
        Get emission order status

        Args:
            order_id: Order ID

        Returns:
            Tuple of (available_codes_count, gtin)
        """
        token = await self.get_suz_token()
        url = f"{settings.crpt_base_url}/api/v3/order/status?omsId={self.oms_id}&orderId={order_id}"
        headers = {
            "Accept": "application/json",
            "clientToken": token
        }

        async with await self._get_http_client() as client:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                if not isinstance(data, list) or not data:
                    raise ValueError("Unexpected response format for order status: expected non-empty list")

                item = data[0]
                quantity = item.get("availableCodes", 0)
                gtin = item.get("gtin")
                return quantity, gtin
            except httpx.HTTPError as e:
                logger.error(f"Failed to get emission status: {e}")
                raise Exception(f"Emission status request failed: {e}")

    async def wait_for_codes(
        self,
        order_id: str,
        timeout: int = 120,
        interval: int = 5
    ):
        """
        Wait for codes to become available

        Args:
            order_id: Order ID
            timeout: Timeout in seconds
            interval: Poll interval in seconds

        Returns:
            Tuple of (quantity, gtin)

        Raises:
            TimeoutError: If codes not available after timeout
        """
        start = time.time()
        while True:
            quantity, gtin = await self.get_emission_status(order_id)
            if quantity and quantity > 0:
                return quantity, gtin

            elapsed = time.time() - start
            if elapsed >= timeout:
                raise TimeoutError(
                    f"Codes not available after {timeout} seconds "
                    f"(last availableCodes={quantity})"
                )

            logger.debug(f"Waiting for codes: availableCodes={quantity}, elapsed={int(elapsed)}s")
            await asyncio.sleep(interval)

    async def get_codes(
        self,
        order_id: str,
        quantity: int,
        gtin: str
    ) -> Tuple[str, List[str]]:
        """
        Get codes from emission order

        Args:
            order_id: Order ID
            quantity: Number of codes to get
            gtin: GTIN

        Returns:
            Tuple of (block_id, codes_list)
        """
        token = await self.get_suz_token()
        url = f"{settings.crpt_base_url}/api/v3/codes"
        params = {
            "omsId": self.oms_id,
            "orderId": order_id,
            "quantity": quantity,
            "gtin": gtin
        }
        headers = {
            "Accept": "application/json",
            "clientToken": token
        }

        async with await self._get_http_client() as client:
            try:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                result = response.json()
                block_id = result['blockId']
                codes = result['codes']
                logger.info(f"Retrieved {len(codes)} codes from order {order_id}")
                return block_id, codes
            except httpx.HTTPError as e:
                logger.error(f"Failed to get codes: {e}")
                raise Exception(f"Get codes request failed: {e}")


    async def send_utilisation_report(
        self,
        product_group: str,
        sntins: List[str],
        utilisation_type: str = "UTILISATION",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send utilisation (apply) report
        """
        # Получаем токен и проверяем его валидность
        token = await self.get_suz_token()
        if not token:
            raise Exception("Failed to get SUZ token")

        url = f"{settings.crpt_base_url}/api/v3/utilisation?omsId={self.oms_id}"

        # Форматируем даты правильно
        formatted_attributes = {}
        if attributes:
            for key, value in attributes.items():
                if hasattr(value, 'strftime'):  # Если это datetime/date объект
                    formatted_attributes[key] = value.strftime("%Y-%m-%d")
                else:
                    formatted_attributes[key] = value

        payload = {
            "productGroup": product_group,
            "utilisationType": utilisation_type,
            "sntins": sntins,
            "attributes": formatted_attributes or {}
        }

        logger.info(f"📤 Sending utilisation report with {len(sntins)} codes")
        logger.info(f"📋 Payload attributes: {formatted_attributes}")

        payload_str = self._canonicalize_json(payload)
        signature = await self.signer.sign_data(payload_str, detached=True)
        signature = signature.replace('\r', '').replace('\n', '')

        headers = {
            "Accept": "application/json",
            "clientToken": token,
            "Content-Type": "application/json",
            "X-Signature": signature
        }

        async with await self._get_http_client() as client:
            try:
                logger.info(f"🔗 Sending POST request to: {url}")
                response = await client.post(url, headers=headers, content=payload_str)

                # Детальное логирование ответа
                logger.info(f"📨 Response status: {response.status_code}")
                if response.status_code != 200:
                    response_text = response.text
                    logger.error(f"❌ Response error: {response_text}")
                    raise Exception(f"Utilisation report failed with status {response.status_code}: {response_text}")

                result = response.json()
                logger.info(f"✅ Utilisation report sent successfully: {result.get('reportId', 'N/A')}")
                return result

            except httpx.HTTPError as e:
                logger.error(f"❌ HTTP error sending utilisation report: {e}")
                # Пытаемся получить больше информации об ошибке
                if hasattr(e, 'response') and e.response:
                    try:
                        error_detail = await e.response.text
                        logger.error(f"❌ Error response: {error_detail}")
                    except:
                        pass
                raise Exception(f"Utilisation report failed: {e}")

    async def get_utilisation_report_status(self, report_id: str) -> Dict[str, Any]:
        """
        Get utilisation report status

        Args:
            report_id: Report ID

        Returns:
            Status JSON
        """
        token = await self.get_suz_token()
        url = f"{settings.crpt_base_url}/api/v3/report/info?omsId={self.oms_id}&reportId={report_id}"
        headers = {
            "Accept": "application/json",
            "clientToken": token
        }

        async with await self._get_http_client() as client:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Failed to get utilisation report status: {e}")
                raise Exception(f"Utilisation report status request failed: {e}")

    async def send_aggregation_report(
        self,
        product_group: str,
        participant_id: str,
        sntins: List[str],
        sscc: str,
        aggregated_items_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send aggregation report

        Args:
            product_group: Product group
            participant_id: Participant INN
            sntins: List of SNTIN codes (cleaned)
            sscc: SSCC code
            aggregated_items_count: Number of aggregated items (default: len(sntins))

        Returns:
            Response JSON
        """
        token = await self.get_suz_token()
        url = f"{settings.crpt_base_url}/api/v3/aggregation?omsId={self.oms_id}"

        # Clean codes
        clean_sntins = [extract_sntin(c) for c in sntins]

        payload = {
            "productGroup": product_group,
            "participantId": participant_id,
            "aggregationUnits": [
                {
                    "aggregatedItemsCount": aggregated_items_count or len(clean_sntins),
                    "aggregationType": "AGGREGATION",
                    "aggregationUnitCapacity": len(clean_sntins),
                    "sntins": clean_sntins,
                    "unitSerialNumber": sscc
                }
            ]
        }

        payload_str = self._canonicalize_json(payload)
        signature = await self.signer.sign_data(payload_str, detached=True)
        signature = signature.replace('\r', '').replace('\n', '')

        headers = {
            "Accept": "application/json",
            "clientToken": token,
            "Content-Type": "application/json",
            "X-Signature": signature
        }

        async with await self._get_http_client() as client:
            try:
                response = await client.post(url, headers=headers, content=payload_str)
                response.raise_for_status()
                result = response.json()
                logger.info(f"Aggregation report sent for SSCC: {sscc}")
                return result
            except httpx.HTTPError as e:
                logger.error(f"Failed to send aggregation report: {e}")
                raise Exception(f"Aggregation report failed: {e}")

    async def check_aggregation_code_status(self, aggr_code: str) -> Tuple[bool, str]:
        """
        Check aggregation code status in TRUE API

        Args:
            aggr_code: Aggregation code (SSCC)

        Returns:
            Tuple of (found, status)
        """
        token = await self.get_true_api_token()
        url = f"{settings.crpt_auth_url}/cises/info?pg=wheelchairs"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = [aggr_code]

        async with await self._get_http_client() as client:
            try:
                response = await client.post(url, headers=headers, json=payload)

                # 404 - это нормально, значит код еще не зарегистрирован
                if response.status_code == 404:
                    return False, "NOT_FOUND"

                response.raise_for_status()
                data = response.json()
                if data and len(data) > 0 and 'cisInfo' in data[0]:
                    cis_info = data[0]['cisInfo']
                    status = cis_info.get('status', 'UNKNOWN')
                    return True, status
                return False, "NOT_FOUND"
            except httpx.HTTPError as e:
                # Логируем только если это не 404
                if hasattr(e, 'response') and e.response and e.response.status_code != 404:
                    logger.error(f"Failed to check aggregation code status: {e}")
                return False, "NOT_FOUND"
            except Exception as e:
                logger.error(f"Unexpected error checking aggregation code status: {e}")
                return False, "ERROR"

    async def send_introduction_report(
        self,
        sscc_codes: List[str],
        participant_inn: str,
        producer_inn: str,
        owner_inn: str,
        production_type: str = "OWN_PRODUCTION",
        product_group: str = "wheelchairs",
    ) -> Dict[str, Any]:
        """
        Send introduction (turnover) report to TRUE API

        Args:
            sscc_codes: List of SSCC codes
            participant_inn: Participant INN
            producer_inn: Producer INN
            owner_inn: Owner INN
            production_type: Production type
            product_group: Product group

        Returns:
            Response with success and document_id
        """
        token = await self.get_true_api_token()
        url = f"{settings.crpt_auth_url}/lk/documents/create?pg={product_group}"

        # Используем структуру из рабочего примера
        document = {
            "participant_inn": participant_inn,
            "producer_inn": producer_inn,
            "owner_inn": owner_inn,
            "production_type": production_type,
            "products": []
        }

        for sscc in sscc_codes:
            product = {
                "uit_code": sscc,  # Используем uit_code вместо cis
                "uit_unit_type": "CARTON",
                "tnved_code": "4015120009",  # Используем tnved_code вместо tnved
            }
            document["products"].append(product)

        document_json = self._canonicalize_json(document)
        document_base64 = base64.b64encode(document_json.encode("utf-8")).decode("utf-8")
        signature_raw = await self.signer.sign_data(document_json, detached=True, cadesbes=True)
        signature_clean = signature_raw.replace("\n", "").replace("\r", "")

        payload = {
            "document_format": "MANUAL",
            "product_document": document_base64,
            "type": "LP_INTRODUCE_GOODS",
            "signature": signature_clean
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        async with await self._get_http_client() as client:
            try:
                logger.info(f"📤 Отправка документа ввода в оборот для SSCC: {sscc_codes}")
                logger.info(f"📋 Структура документа: {document}")

                response = await client.post(url, headers=headers, json=payload)

                # Детальное логирование ответа
                logger.info(f"📨 Response status: {response.status_code}")
                if response.status_code not in (200, 201):
                    response_text = response.text
                    logger.error(f"❌ Response error: {response_text}")
                    return {"success": False, "error": f"Introduction report failed with status {response.status_code}: {response_text}"}

                try:
                    js = response.json()
                    if isinstance(js, dict):
                        document_id = js.get('document_id') or js.get('id') or str(js)
                    else:
                        document_id = str(js)
                except:
                    document_id = response.text.strip()

                logger.info(f"✅ Introduction report sent, document_id: {document_id}")
                return {"success": True, "document_id": document_id}
            except httpx.HTTPError as e:
                error_text = e.response.text if hasattr(e, 'response') else str(e)
                logger.error(f"❌ Failed to send introduction report: {e}")
                return {"success": False, "error": error_text}

    async def close_order(self, order_id: str) -> bool:
        """Send order CLOSE request to SUZ"""

        logger.info(f"Попытка закрыть заказ в СУЗ: {order_id}")

        try:
            token = await self.get_suz_token()
            url = f"{settings.crpt_base_url}/api/v3/order/close?omsId={self.oms_id}"

            payload = {
                "orderId": order_id
            }
            payload_str = self._canonicalize_json(payload)

            signature = await self.signer.sign_data(payload_str, detached=True)
            signature = signature.replace('\r', '').replace('\n', '')

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "clientToken": token,
                "X-Signature": signature
            }

            async with await self._get_http_client() as client:
                try:
                    response = await client.post(url, headers=headers, content=payload_str)
                    response.raise_for_status()

                    if response.status_code == 200:
                        logger.info(f"Заказ {order_id} успешно закрыт в СУЗ")
                        return True
                    else:
                        logger.warning(f"Неожиданный статус ответа СУЗ: {response.status_code}")
                        return False

                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP ошибка при закрытии заказа {order_id}: {e}")
                    if e.response:
                        logger.error(f"Ответ СУЗ: {e.response.text}")
                    return False
                except httpx.TimeoutException:
                    logger.error(f"Таймаут при закрытии заказа {order_id}")
                    return False
                except httpx.NetworkError:
                    logger.error(f"Сетевая ошибка при закрытии заказа {order_id}")
                    return False
                except httpx.HTTPError as e:
                    logger.error(f"HTTP ошибка при закрытии заказа {order_id}: {e}")
                    return False

        except Exception as e:
            logger.exception(f"Непредвиденная ошибка при закрытии заказа {order_id}: {e}")
            return False
