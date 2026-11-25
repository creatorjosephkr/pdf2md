import React from "react";
import { ExternalLink, X } from "lucide-react";
import { openExternalUrl } from "../api/client";

const PAYPAL_URL = "https://www.paypal.com/paypalme/tech1010?locale.x=ko_KR&country.x=KR";

export const SponsorIcon: React.FC<{ className?: string }> = ({ className = "h-6 w-6" }) => (
  <svg
    viewBox="0 0 256 256"
    fill="currentColor"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    aria-hidden="true"
  >
    <path d="M212.69,105.32c-2.11,0-3.82,1.7-3.81,3.79,0,2.07,1.71,3.75,3.81,3.76,4.27,0,7.66,3.35,7.66,7.55,0,2.23-.65,3.51-1.92,4.71-1.27,1.2-3.4,2.24-6.3,2.87-7.11,1.31-14.94.39-21.44-1-3.27-.7-6.21-1.51-8.59-2.17-4.7-1.4-9.53-1.75-13.78-1.84-10.52,0-19.13,8.48-19.13,18.86,0,5.19,2.13,9.93,5.59,13.34,1.5,1.48,3.93,1.48,5.43,0,1.5-1.47,1.5-3.88,0-5.35-2.08-2.05-3.36-4.84-3.36-7.99,0-6.02,4.66-10.88,10.65-11.28,4.21-.29,8.99.6,12.51,1.5,2.4.67,5.51,1.56,9.04,2.31,7.06,1.51,15.86,2.67,24.6,1.03,3.78-1.19,7.63-2.57,10.08-4.82,2.66-2.51,4.27-6.15,4.27-10.17,0-8.28-6.9-15.09-15.31-15.09h0Z" />
    <path d="M168.31,110.31c-10.15.13-16.76,4.37-16.76,4.37-1.75,1.16-2.22,3.5-1.04,5.23,1.17,1.74,3.54,2.21,5.31,1.06,0,0,7.61-5.24,19.97-2.28,2.05.5,4.13-.73,4.63-2.76.51-2.03-.76-4.08-2.83-4.57-3.33-.8-6.45-1.09-9.29-1.05h0Z" />
    <path d="M166.52,139.44c-.87.05-1.69.38-2.34.95-1.59,1.39-1.73,3.79-.31,5.35,0,0,5.63,5.95,15.74,6.6,2.11.13,3.94-1.45,4.07-3.54.14-2.08-1.45-3.87-3.56-4.02-7.48-.48-10.54-4.09-10.54-4.09-.67-.74-1.62-1.2-2.63-1.25-.14-.01-.28-.01-.43,0h0Z" />
    <path d="M189.96,209.11h7.41c3.15,0,6.91-1.19,10.03-4.26,3.12-3.07,5.28-7.97,5.28-14.59s-2.16-11.56-5.28-14.63c-3.12-3.07-6.88-4.23-10.03-4.23h-4.48c-1.59-4.38-5.87-7.55-10.83-7.55h-53.56c-6.3,0-11.5,5.1-11.5,11.31v18.86c0,10.66,5.03,20.2,12.86,26.44h-16.67c-2.11,0-3.83,1.67-3.84,3.76,0,2.1,1.72,3.8,3.84,3.79h88.02c2.11,0,3.82-1.7,3.81-3.79,0-2.07-1.71-3.75-3.81-3.76h-20.5c3.85-3.07,7.02-6.94,9.25-11.34ZM193.57,194.01v-15.1h3.81c1.08,0,3.07.52,4.63,2.06,1.57,1.54,3.02,4.19,3.02,9.28s-1.45,7.73-3.02,9.27c-1.57,1.54-3.55,2.03-4.63,2.03h-4.68c.56-2.43.87-4.95.87-7.55ZM159.13,220.45h-7.65c-14.84,0-26.81-11.8-26.81-26.44v-18.86c0-2.13,1.68-3.76,3.84-3.76h53.56c2.16,0,3.84,1.63,3.84,3.76v18.86c0,14.63-11.94,26.44-26.78,26.44Z" />
    <path d="M95.61,28c-27.96,0-50.7,22.42-50.7,50s22.74,50,50.7,50,50.7-22.42,50.7-50-22.74-50-50.7-50ZM95.61,111.33c-18.64,0-33.8-14.95-33.8-33.33s15.16-33.33,33.8-33.33,33.8,14.95,33.8,33.33-15.16,33.33-33.8,33.33Z" />
    <path d="M103.85,144.67l2.48,16.67h-36.08c-13.98,0-25.35,11.22-25.35,25v41.67h-16.9v-41.67c0-22.97,18.95-41.67,42.25-41.67h33.6Z" />
  </svg>
);

interface SponsorModalProps {
  open: boolean;
  onClose: () => void;
}

export const SponsorModal: React.FC<SponsorModalProps> = ({ open, onClose }) => {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 p-4 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl rounded-2xl border border-slate-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100 text-slate-700">
              <SponsorIcon className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">PDF 얼개 후원하기</h2>
              <p className="text-xs text-slate-500">개발과 유지보수에 큰 힘이 됩니다</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 cursor-pointer"
            aria-label="닫기"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body: Left KakaoBank QR | Right PayPal */}
        <div className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2">
          {/* Left: KakaoBank */}
          <div className="flex flex-col items-center justify-between rounded-xl border border-slate-200 bg-slate-50/70 p-4 text-center">
            <div className="text-sm font-bold text-slate-900">카카오뱅크</div>
            <div className="my-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-2xs">
              <img
                src="/spon/kakaobank.png"
                alt="카카오뱅크 후원 QR"
                className="h-44 w-44 object-contain select-none"
                draggable={false}
              />
            </div>
            <p className="text-xs leading-relaxed text-slate-600">
              카카오뱅크 앱 또는 카메라로 QR 코드를 스캔해 주세요.
            </p>
          </div>

          {/* Right: PayPal */}
          <div className="flex flex-col items-center justify-between rounded-xl border border-slate-200 bg-slate-50/70 p-4 text-center">
            <div className="text-sm font-bold text-slate-900">PayPal</div>
            <button
              type="button"
              onClick={() => void openExternalUrl(PAYPAL_URL)}
              className="my-3 flex h-[202px] w-[202px] items-center justify-center rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs transition-all hover:border-blue-300 hover:shadow-sm cursor-pointer"
              title="PayPal 후원 페이지 열기"
            >
              <img
                src="/spon/paypal.png"
                alt="PayPal 후원"
                className="h-24 w-24 object-contain select-none"
                draggable={false}
              />
            </button>
            <button
              type="button"
              onClick={() => void openExternalUrl(PAYPAL_URL)}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 cursor-pointer"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              PayPal로 후원하기
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
