import { useState, useCallback } from 'react';
import { autoParse, parseExcel } from '../utils/dataParser';

export interface UseDataParserState {
  rawText: string;
  parsedData: Record<string, unknown>[];
  columns: string[];
  error: string | null;
}

export function useDataParser() {
  const [state, setState] = useState<UseDataParserState>({
    rawText: '',
    parsedData: [],
    columns: [],
    error: null,
  });

  const parse = useCallback((text: string): boolean => {
    try {
      const data = autoParse(text);
      if (data.length === 0) {
        throw new Error('未解析到有效数据，请检查数据格式或分隔符');
      }
      const columns =
        data.length > 0 ? Object.keys(data[0]) : [];

      setState({
        rawText: text,
        parsedData: data,
        columns,
        error: null,
      });
      return true;
    } catch (err) {
      setState({
        rawText: text,
        parsedData: [],
        columns: [],
        error:
          err instanceof Error ? err.message : 'Failed to parse data',
      });
      return false;
    }
  }, []);

  const parseWorkbook = useCallback((buffer: ArrayBuffer, filename = ''): boolean => {
    try {
      const data = parseExcel(buffer);
      if (data.length === 0) {
        throw new Error('未解析到有效数据，请检查工作簿内容');
      }
      const columns =
        data.length > 0 ? Object.keys(data[0]) : [];

      setState({
        rawText: filename,
        parsedData: data,
        columns,
        error: null,
      });
      return true;
    } catch (err) {
      setState({
        rawText: filename,
        parsedData: [],
        columns: [],
        error:
          err instanceof Error ? err.message : 'Failed to parse workbook',
      });
      return false;
    }
  }, []);

  const clear = useCallback((): void => {
    setState({
      rawText: '',
      parsedData: [],
      columns: [],
      error: null,
    });
  }, []);

  const fail = useCallback((error: string, rawText = ''): void => {
    setState({
      rawText,
      parsedData: [],
      columns: [],
      error,
    });
  }, []);

  return {
    ...state,
    parse,
    parseWorkbook,
    clear,
    fail,
  };
}

export default useDataParser;
