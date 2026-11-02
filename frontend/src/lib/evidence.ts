/**
 * 할 일 완료 증빙 1장 고르기 (FR-029). 휴대폰은 카메라로 찍거나 앨범에서 고르고, 파일(사진·PDF)에서도 고른다. 웹은 파일을 고른다.
 * 서버는 형식·화질을 제한하지 않고 20MB까지 받으므로 사진만 화질을 조금 낮춰 보낸다.
 * 인터넷등기소 열람본·임대차 신고필증·보증서·이체 확인증처럼 PDF로 받는 서류가 많아 파일 고르기를 둔다 (DATA-06)
 */
import * as DocumentPicker from 'expo-document-picker';
import { Directory, File, Paths } from 'expo-file-system';
import * as ImagePicker from 'expo-image-picker';
import * as Sharing from 'expo-sharing';
import { Platform } from 'react-native';

import type { PickedFile } from '@/lib/api';

export type EvidenceSource = 'camera' | 'library' | 'file';

const OPTIONS: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.7 };

/** 파일 고르기에서 고를 수 있는 형식 */
const FILE_TYPES = ['image/*', 'application/pdf'];

/** 파일(사진·PDF) 1개. 고르지 않고 닫으면 null */
async function pickFile(): Promise<PickedFile | null> {
  const res = await DocumentPicker.getDocumentAsync({ type: FILE_TYPES, copyToCacheDirectory: true });
  const asset = res.canceled ? null : res.assets[0];
  if (!asset) return null;
  return { uri: asset.uri, name: asset.name, mimeType: asset.mimeType ?? null };
}

/** 증빙 1개. 고르지 않고 닫으면 null, 권한을 거절하면 throw */
export async function pickEvidence(source: EvidenceSource): Promise<PickedFile | null> {
  if (source === 'file') return pickFile();
  // 웹은 카메라 대신 파일 선택 (휴대폰 브라우저는 선택 창에서 카메라도 고를 수 있음)
  const camera = source === 'camera' && Platform.OS !== 'web';
  if (camera) {
    const { granted } = await ImagePicker.requestCameraPermissionsAsync();
    if (!granted) throw new Error('카메라 권한이 없어요. 설정에서 허용하거나 앨범에서 골라 주세요');
  }
  const result = camera
    ? await ImagePicker.launchCameraAsync(OPTIONS)
    : await ImagePicker.launchImageLibraryAsync(OPTIONS);
  const asset = result.canceled ? null : result.assets[0];
  if (!asset) return null;
  const type = asset.mimeType ?? 'image/jpeg';
  return { uri: asset.uri, name: asset.fileName ?? `evidence.${type.split('/')[1] ?? 'jpg'}`, mimeType: type };
}

/**
 * 올린 증빙·서류 파일을 연다 (사진이 아니라 화면에서 미리 볼 수 없는 PDF 등). 계약 토큰 헤더가 필요해 주소를 바로 열 수 없으므로
 * 웹은 받아서 새 탭으로, 휴대폰은 받아서 공유 창(PDF 보기·파일에 저장)으로 연다
 */
export async function openEvidenceFile(source: { uri: string; headers: Record<string, string> }): Promise<void> {
  if (Platform.OS === 'web') {
    // 받은 뒤에 열면 팝업 차단에 걸리니 탭을 먼저 연다
    const tab = window.open('', '_blank');
    try {
      const res = await fetch(source.uri, { headers: source.headers });
      if (!res.ok) throw new Error();
      const url = URL.createObjectURL(await res.blob());
      if (tab) tab.location.href = url;
      else window.location.assign(url);
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      tab?.close();
      throw new Error('파일을 받지 못했어요');
    }
    return;
  }
  if (!(await Sharing.isAvailableAsync())) throw new Error('이 기기에서는 파일을 열 수 없어요');
  const dir = new Directory(Paths.cache, 'evidence');
  if (!dir.exists) dir.create();
  // 이름은 서버가 준 이름(evidence-T1.pdf 등). 같은 이름이 있으면 덮어쓴다
  const file = await File.downloadFileAsync(source.uri, dir, { headers: source.headers, idempotent: true });
  const pdf = file.name.toLowerCase().endsWith('.pdf');
  await Sharing.shareAsync(file.uri, {
    mimeType: pdf ? 'application/pdf' : undefined,
    UTI: pdf ? 'com.adobe.pdf' : undefined,
    dialogTitle: '파일 열기',
  });
}
