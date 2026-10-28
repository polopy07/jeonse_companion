/**
 * 할 일 완료 증빙 사진 1장 고르기 (FR-029). 휴대폰은 카메라로 찍거나 앨범에서 고르고, 웹은 파일을 고른다.
 * 서버는 형식·화질을 제한하지 않고 20MB까지 받으므로 화질만 조금 낮춰 보낸다.
 */
import * as ImagePicker from 'expo-image-picker';
import { Platform } from 'react-native';

import type { PickedFile } from '@/lib/api';

export type EvidenceSource = 'camera' | 'library';

const OPTIONS: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.7 };

/** 사진 1장. 고르지 않고 닫으면 null, 권한을 거절하면 throw */
export async function pickEvidence(source: EvidenceSource): Promise<PickedFile | null> {
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
