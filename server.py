#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import logging
import os
import sys
import subprocess
import shlex
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

import websockets
from websockets.server import WebSocketServerProtocol

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class RustAnalyzerBridge:
    """Класс для связи с внешним rust-analyzer"""
    
    def __init__(self, rust_analyzer_path: str = "rust-analyzer"):
        """
        Инициализация моста с rust-analyzer
        
        Args:
            rust_analyzer_path: Путь к исполняемому файлу rust-analyzer
        """
        self.rust_analyzer_path = rust_analyzer_path
        self.process = None
        self.request_id = 0
        
    async def start(self):
        """Запуск процесса rust-analyzer"""
        try:
            # Запускаем rust-analyzer в режиме LSP
            self.process = await asyncio.create_subprocess_exec(
                self.rust_analyzer_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            logger.info(f"Запущен rust-analyzer (PID: {self.process.pid})")
            return True
        except Exception as e:
            logger.error(f"Ошибка запуска rust-analyzer: {e}")
            return False
            
    async def stop(self):
        """Остановка процесса rust-analyzer"""
        if self.process and self.process.returncode is None:
            try:
                # Отправляем запрос shutdown
                await self._send_request("shutdown", {})
                # Отправляем уведомление exit
                await self._send_notification("exit", None)
                # Даем процессу время на завершение
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    # Если процесс не завершился по-хорошему, завершаем его принудительно
                    self.process.terminate()
                    await self.process.wait()
                logger.info("rust-analyzer остановлен")
            except Exception as e:
                logger.error(f"Ошибка при остановке rust-analyzer: {e}")
                if self.process and self.process.returncode is None:
                    self.process.kill()
                    
    async def _send_request(self, method: str, params: Any) -> Optional[Dict]:
        """
        Отправка LSP запроса к rust-analyzer
        
        Args:
            method: Метод LSP
            params: Параметры запроса
            
        Returns:
            Результат запроса или None в случае ошибки
        """
        if not self.process or self.process.returncode is not None:
            logger.error("rust-analyzer не запущен")
            return None
            
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params
        }
        
        # Формируем заголовок Content-Length для LSP
        content = json.dumps(request)
        content_length = len(content.encode('utf-8'))
        header = f"Content-Length: {content_length}\r\n\r\n"
        
        try:
            # Отправляем запрос
            self.process.stdin.write(header.encode('ascii') + content.encode('utf-8'))
            await self.process.stdin.drain()
            
            # Читаем ответ
            header_data = await self.process.stdout.readuntil(b"\r\n\r\n")
            header_text = header_data.decode('ascii')
            
            # Извлекаем Content-Length
            content_length = int(header_text.split(": ")[1])
            
            # Читаем тело ответа
            content_data = await self.process.stdout.readexactly(content_length)
            response = json.loads(content_data)
            
            if "error" in response:
                logger.error(f"Ошибка LSP: {response['error']}")
                return None
                
            return response.get("result")
        except Exception as e:
            logger.error(f"Ошибка отправки запроса: {e}")
            return None
            
    async def _send_notification(self, method: str, params: Any):
        """
        Отправка LSP уведомления к rust-analyzer
        
        Args:
            method: Метод LSP
            params: Параметры уведомления
        """
        if not self.process or self.process.returncode is not None:
            logger.error("rust-analyzer не запущен")
            return
            
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        # Формируем заголовок Content-Length для LSP
        content = json.dumps(notification)
        content_length = len(content.encode('utf-8'))
        header = f"Content-Length: {content_length}\r\n\r\n"
        
        try:
            # Отправляем уведомление
            self.process.stdin.write(header.encode('ascii') + content.encode('utf-8'))
            await self.process.stdin.drain()
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
            
    async def initialize(self, root_uri: str, capabilities: Dict = None):
        """
        Инициализация LSP-сессии
        
        Args:
            root_uri: URI корневой директории проекта
            capabilities: Возможности клиента
            
        Returns:
            Возможности сервера или None в случае ошибки
        """
        if not capabilities:
            capabilities = {
                "textDocument": {
                    "completion": {
                        "completionItem": {
                            "snippetSupport": True
                        }
                    },
                    "hover": {},
                    "signatureHelp": {},
                    "references": {},
                    "definition": {},
                    "implementation": {},
                    "documentHighlight": {},
                    "documentSymbol": {},
                    "formatting": {},
                    "codeAction": {},
                    "rename": {}
                },
                "workspace": {
                    "symbol": {}
                }
            }
            
        params = {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "capabilities": capabilities,
            "trace": "verbose"
        }
        
        return await self._send_request("initialize", params)
        
    async def initialized(self):
        """Отправка уведомления initialized"""
        await self._send_notification("initialized", {})
        
    async def analyze_file(self, uri: str, text: str):
        """
        Анализ содержимого файла
        
        Args:
            uri: URI файла
            text: Содержимое файла
            
        Returns:
            Результаты анализа или None в случае ошибки
        """
        # Уведомляем rust-analyzer о содержимом файла
        await self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "rust",
                "version": 1,
                "text": text
            }
        })
        
        # Запрашиваем диагностику
        diagnostics = await self._send_request("textDocument/publishDiagnostics", {
            "uri": uri
        })
        
        # Запрашиваем символы документа
        symbols = await self._send_request("textDocument/documentSymbol", {
            "textDocument": {
                "uri": uri
            }
        })
        
        return {
            "diagnostics": diagnostics,
            "symbols": symbols
        }


class LanguageServer:
    """WebSocket сервер для LSP"""
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        """
        Инициализация сервера
        
        Args:
            host: Хост для прослушивания
            port: Порт для прослушивания
        """
        self.host = host
        self.port = port
        self.clients = {}  # {client_id: {"websocket": ws, "workspace": workspace}}
        self.analyzers = {}  # {client_id: RustAnalyzerBridge}
        self.next_client_id = 1
        
    async def start(self):
        """Запуск WebSocket сервера"""
        logger.info(f"Запуск языкового сервера на {self.host}:{self.port}")
        async with websockets.serve(self.handle_client, self.host, self.port):
            await asyncio.Future()  # Работать бесконечно
            
    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """
        Обработка соединения клиента
        
        Args:
            websocket: WebSocket соединение
            path: Путь соединения
        """
        client_id = str(self.next_client_id)
        self.next_client_id += 1
        
        # Регистрируем клиента
        self.clients[client_id] = {"websocket": websocket, "workspace": None}
        logger.info(f"Новое соединение: клиент {client_id}")
        
        try:
            # Создаем и запускаем анализатор для клиента
            analyzer = RustAnalyzerBridge()
            if await analyzer.start():
                self.analyzers[client_id] = analyzer
                
                # Обрабатываем сообщения от клиента
                async for message in websocket:
                    await self.process_message(client_id, message)
            else:
                await websocket.send(json.dumps({
                    "error": "Не удалось запустить rust-analyzer"
                }))
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Соединение закрыто: клиент {client_id}")
        except Exception as e:
            logger.error(f"Ошибка при обработке клиента {client_id}: {e}")
        finally:
            # Освобождаем ресурсы
            if client_id in self.analyzers:
                await self.analyzers[client_id].stop()
                del self.analyzers[client_id]
            if client_id in self.clients:
                del self.clients[client_id]
                
    async def process_message(self, client_id: str, message: str):
        """
        Обработка сообщения от клиента
        
        Args:
            client_id: ID клиента
            message: Полученное сообщение
        """
        try:
            data = json.loads(message)
            command = data.get("command")
            params = data.get("params", {})
            
            result = None
            
            if command == "initialize":
                # Инициализация рабочей области
                workspace_path = params.get("workspacePath")
                if workspace_path:
                    # Преобразуем путь в URI
                    workspace_uri = Path(workspace_path).as_uri()
                    self.clients[client_id]["workspace"] = workspace_uri
                    
                    # Инициализируем LSP-сессию
                    result = await self.analyzers[client_id].initialize(workspace_uri)
                    await self.analyzers[client_id].initialized()
                else:
                    result = {"error": "Не указан путь к рабочей области"}
                    
            elif command == "analyze":
                # Анализ файла
                file_path = params.get("filePath")
                file_content = params.get("content")
                
                if not file_path or not file_content:
                    result = {"error": "Не указан путь к файлу или его содержимое"}
                else:
                    # Преобразуем путь в URI
                    file_uri = Path(file_path).as_uri()
                    result = await self.analyzers[client_id].analyze_file(file_uri, file_content)
                    
            elif command == "complete":
                # Автодополнение
                file_path = params.get("filePath")
                position = params.get("position")  # {line, character}
                
                if not file_path or not position:
                    result = {"error": "Не указан путь к файлу или позиция курсора"}
                else:
                    file_uri = Path(file_path).as_uri()
                    completion_params = {
                        "textDocument": {"uri": file_uri},
                        "position": position
                    }
                    result = await self.analyzers[client_id]._send_request(
                        "textDocument/completion", completion_params
                    )
                    
            elif command == "hover":
                # Подсказка при наведении
                file_path = params.get("filePath")
                position = params.get("position")
                
                if not file_path or not position:
                    result = {"error": "Не указан путь к файлу или позиция курсора"}
                else:
                    file_uri = Path(file_path).as_uri()
                    hover_params = {
                        "textDocument": {"uri": file_uri},
                        "position": position
                    }
                    result = await self.analyzers[client_id]._send_request(
                        "textDocument/hover", hover_params
                    )
                    
            elif command == "definition":
                # Переход к определению
                file_path = params.get("filePath")
                position = params.get("position")
                
                if not file_path or not position:
                    result = {"error": "Не указан путь к файлу или позиция курсора"}
                else:
                    file_uri = Path(file_path).as_uri()
                    definition_params = {
                        "textDocument": {"uri": file_uri},
                        "position": position
                    }
                    result = await self.analyzers[client_id]._send_request(
                        "textDocument/definition", definition_params
                    )
                    
            else:
                result = {"error": f"Неизвестная команда: {command}"}
                
            # Отправляем результат клиенту
            await self.clients[client_id]["websocket"].send(json.dumps({
                "id": data.get("id"),
                "result": result
            }))
            
        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON от клиента {client_id}")
            await self.clients[client_id]["websocket"].send(json.dumps({
                "error": "Неверный формат JSON"
            }))
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения от клиента {client_id}: {e}")
            await self.clients[client_id]["websocket"].send(json.dumps({
                "error": str(e)
            }))


if __name__ == "__main__":
    # Парсинг аргументов командной строки
    import argparse
    parser = argparse.ArgumentParser(description="WebSocket сервер для Rust Analyzer")
    parser.add_argument("--host", default="localhost", help="Хост для прослушивания")
    parser.add_argument("--port", type=int, default=8765, help="Порт для прослушивания")
    parser.add_argument("--rust-analyzer-path", default="rust-analyzer", 
                      help="Путь к исполняемому файлу rust-analyzer")
    args = parser.parse_args()
    
    # Устанавливаем путь к rust-analyzer как значение по умолчанию
    RustAnalyzerBridge.rust_analyzer_path = args.rust_analyzer_path
    
    # Запускаем сервер
    server = LanguageServer(args.host, args.port)
    
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Сервер остановлен")