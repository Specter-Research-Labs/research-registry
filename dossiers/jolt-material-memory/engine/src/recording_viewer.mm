// SPDX-License-Identifier: MIT

#include <TestFramework.h>

#include <Renderer/DebugRendererImp.h>
#include <Renderer/Font.h>
#include <Renderer/Renderer.h>
#include <Renderer/MTL/RendererMTL.h>
#include <Window/ApplicationWindowMacOS.h>
#include <Input/MacOS/KeyboardMacOS.h>
#include <Input/MacOS/MouseMacOS.h>
#include <Utils/Log.h>
#include <Jolt/Core/Factory.h>
#include <Jolt/Core/FPException.h>
#include <Jolt/Core/Memory.h>
#include <Jolt/Core/StreamWrapper.h>
#include <Jolt/RegisterTypes.h>

#ifdef JPH_DEBUG_RENDERER
	#include <Jolt/Renderer/DebugRendererPlayback.h>
#else
	#define JPH_DEBUG_RENDERER
	#define JPH_DEBUG_RENDERER_EXPORT
	#include <Jolt/Renderer/DebugRendererPlayback.h>
	#undef JPH_DEBUG_RENDERER
	#undef JPH_DEBUG_RENDERER_EXPORT
#endif

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include <Cocoa/Cocoa.h>

using Clock = chrono::high_resolution_clock;
namespace fs = std::filesystem;

namespace
{
constexpr uint kInvalidFrame = numeric_limits<uint>::max();

struct ViewerConfig
{
	string recording_path;
	optional<RVec3> camera_pos;
	optional<Vec3> camera_forward;
	Vec3 camera_up = Vec3(0, 1, 0);
	float fov_y_radians = DegreesToRadians(55.0f);
	float playback_fps = 60.0f;
	bool autoplay = false;
	bool stop_after_last_frame = false;
	bool export_frames = false;
	bool show_axis = true;
	bool lock_camera = false;
	fs::path frames_out_dir;
};

bool ParseFloat(const char *inValue, float &outValue)
{
	char *end = nullptr;
	double parsed = strtod(inValue, &end);
	if (end == inValue || *end != '\0' || !isfinite(parsed))
		return false;
	outValue = static_cast<float>(parsed);
	return true;
}

bool ParsePositiveFloat(const char *inValue, float &outValue)
{
	if (!ParseFloat(inValue, outValue))
		return false;
	return outValue > 0.0f;
}

bool ParseVec3(const char *inValue, Vec3 &outValue)
{
	float x = 0.0f;
	float y = 0.0f;
	float z = 0.0f;
	if (sscanf(inValue, "%f,%f,%f", &x, &y, &z) != 3)
		return false;
	outValue = Vec3(x, y, z);
	return true;
}

bool ParseRVec3(const char *inValue, RVec3 &outValue)
{
	float x = 0.0f;
	float y = 0.0f;
	float z = 0.0f;
	if (sscanf(inValue, "%f,%f,%f", &x, &y, &z) != 3)
		return false;
	outValue = RVec3(x, y, z);
	return true;
}

void PrintUsage(FILE *inStream)
{
	fprintf(
		inStream,
		"Usage: JoltRecordingViewer <recording.jor> [options]\n"
		"  --camera-pos x,y,z\n"
		"  --camera-target x,y,z\n"
		"  --camera-forward x,y,z\n"
		"  --camera-up x,y,z\n"
		"  --fov degrees\n"
		"  --fps hz\n"
		"  --autoplay\n"
		"  --frames-out dir\n"
		"  --stop-after-last-frame\n"
		"  --help\n"
	);
}

optional<ViewerConfig> ParseArgs(int inArgC, char **inArgV)
{
	if (inArgC < 2)
		return nullopt;

	ViewerConfig config;
	optional<RVec3> camera_target;

	for (int i = 1; i < inArgC; ++i)
	{
		string_view arg = inArgV[i];
		if (arg == "--help")
		{
			PrintUsage(stdout);
			return nullopt;
		}
		if (arg == "--camera-pos")
		{
			if (++i >= inArgC || !ParseRVec3(inArgV[i], config.camera_pos.emplace()))
				return nullopt;
			continue;
		}
		if (arg == "--camera-target")
		{
			if (++i >= inArgC || !ParseRVec3(inArgV[i], camera_target.emplace()))
				return nullopt;
			continue;
		}
		if (arg == "--camera-forward")
		{
			Vec3 parsed;
			if (++i >= inArgC || !ParseVec3(inArgV[i], parsed) || parsed.IsNearZero())
				return nullopt;
			config.camera_forward = parsed.Normalized();
			continue;
		}
		if (arg == "--camera-up")
		{
			if (++i >= inArgC || !ParseVec3(inArgV[i], config.camera_up) || config.camera_up.IsNearZero())
				return nullopt;
			config.camera_up = config.camera_up.Normalized();
			continue;
		}
		if (arg == "--fov")
		{
			float degrees = 0.0f;
			if (++i >= inArgC || !ParsePositiveFloat(inArgV[i], degrees))
				return nullopt;
			config.fov_y_radians = DegreesToRadians(degrees);
			continue;
		}
		if (arg == "--fps")
		{
			if (++i >= inArgC || !ParsePositiveFloat(inArgV[i], config.playback_fps))
				return nullopt;
			continue;
		}
		if (arg == "--autoplay")
		{
			config.autoplay = true;
			continue;
		}
		if (arg == "--frames-out")
		{
			if (++i >= inArgC)
				return nullopt;
			config.frames_out_dir = inArgV[i];
			config.export_frames = true;
			continue;
		}
		if (arg == "--stop-after-last-frame")
		{
			config.stop_after_last_frame = true;
			continue;
		}
		if (arg.starts_with("--"))
		{
			return nullopt;
		}
		if (!config.recording_path.empty())
			return nullopt;
		config.recording_path = inArgV[i];
	}

	if (config.recording_path.empty())
		return nullopt;

	if (camera_target.has_value())
	{
		if (!config.camera_pos.has_value())
			return nullopt;
		Vec3 forward = Vec3(camera_target->GetX() - config.camera_pos->GetX(), camera_target->GetY() - config.camera_pos->GetY(), camera_target->GetZ() - config.camera_pos->GetZ());
		if (forward.IsNearZero())
			return nullopt;
		config.camera_forward = forward.Normalized();
	}

	if (config.camera_pos.has_value() != config.camera_forward.has_value())
		return nullopt;

	config.lock_camera = config.camera_pos.has_value();
	if (config.export_frames)
	{
		config.show_axis = false;
		if (!config.stop_after_last_frame)
			config.stop_after_last_frame = true;
	}

	return config;
}

bool SaveMainWindowPng(const fs::path &inPath)
{
	NSWindow *window = [NSApp mainWindow];
	if (window == nil)
		return false;

	NSView *content_view = window.contentView;
	if (content_view == nil)
		return false;

	NSBitmapImageRep *bitmap = [content_view bitmapImageRepForCachingDisplayInRect: content_view.bounds];
	if (bitmap == nil)
		return false;
	[content_view cacheDisplayInRect: content_view.bounds toBitmapImageRep: bitmap];

	NSDictionary *properties = [NSDictionary dictionary];
	NSData *png = [bitmap representationUsingType: NSBitmapImageFileTypePNG properties: properties];
	[bitmap release];
	if (png == nil)
		return false;

	NSString *path = [NSString stringWithUTF8String: inPath.string().c_str()];
	return [png writeToFile: path atomically: YES];
}

void ConfigureWindowForCapture()
{
	NSWindow *window = [NSApp mainWindow];
	if (window == nil)
		return;

	window.titleVisibility = NSWindowTitleHidden;
	window.titlebarAppearsTransparent = YES;
	window.styleMask = window.styleMask | NSWindowStyleMaskFullSizeContentView;
	for (NSWindowButton button : { NSWindowCloseButton, NSWindowMiniaturizeButton, NSWindowZoomButton })
		[[window standardWindowButton: button] setHidden: YES];
}
}

class RecordingViewerApp
{
public:
	explicit RecordingViewerApp(ViewerConfig inConfig) :
		mConfig(std::move(inConfig))
	{
		Trace = TraceImpl;

#ifdef JPH_ENABLE_ASSERTS
		AssertFailed = [](const char *inExpression, const char *inMessage, const char *inFile, uint inLine)
		{
			Trace("%s (%d): Assert Failed: %s", inFile, inLine, inMessage != nullptr? inMessage : inExpression);
			return true;
		};
#endif

		Factory::sInstance = new Factory;
		RegisterTypes();

		mWindow = new ApplicationWindowMacOS;
		mWindow->Initialize("Jolt Recording Viewer");

		mRenderer = Renderer::sCreate();
		mRenderer->Initialize(mWindow);

		mFont = new Font(mRenderer);
		mFont->Create("Roboto-Regular", 24);

		mDebugRenderer = new DebugRendererImp(mRenderer, mFont);
		mRendererPlayback = make_unique<DebugRendererPlayback>(*mDebugRenderer);

		mKeyboard = new KeyboardMacOS;
		mKeyboard->Initialize(mWindow);

		mMouse = new MouseMacOS;
		mMouse->Initialize(mWindow);

		ifstream stream(mConfig.recording_path.c_str(), ifstream::in | ifstream::binary);
		if (!stream.is_open())
			FatalError("Could not open recording file: %s", mConfig.recording_path.c_str());

		StreamInWrapper wrapper(stream);
		mRendererPlayback->Parse(wrapper);
		if (mRendererPlayback->GetNumFrames() == 0)
			FatalError("Recording file did not contain any frames");

		mCurrentFrame = 0;
		mCamera.mPos = RVec3(8.0, 4.5, 16.0);
		mCamera.mForward = Vec3(-0.45f, -0.12f, -0.88f).Normalized();
		mCamera.mUp = Vec3(0, 1, 0);
		mCamera.mFOVY = mConfig.fov_y_radians;
		if (mConfig.lock_camera)
		{
			mCamera.mPos = *mConfig.camera_pos;
			mCamera.mForward = mConfig.camera_forward->Normalized();
			mCamera.mUp = mConfig.camera_up.Normalized();
		}

		if (mConfig.export_frames)
			fs::create_directories(mConfig.frames_out_dir);

		if (auto *renderer_mtl = dynamic_cast<RendererMTL *>(mRenderer))
			renderer_mtl->GetView().framebufferOnly = NO;

		mPaused = !mConfig.autoplay;
		mRequestedDeltaTime = 1.0f / mConfig.playback_fps;
		mLastUpdateTime = Clock::now();
	}

	~RecordingViewerApp()
	{
		delete mMouse;
		delete mKeyboard;
		mRendererPlayback.reset();
		delete mDebugRenderer;
		mFont = nullptr;
		delete mRenderer;
		delete mWindow;
		UnregisterTypes();
		delete Factory::sInstance;
		Factory::sInstance = nullptr;
	}

	void Run()
	{
		mWindow->MainLoop([this]() { return RenderFrame(); });
	}

private:
	bool RenderFrame()
	{
		MaybeConfigureCaptureWindow();
		mKeyboard->Poll();
		mMouse->Poll();

		if (CapturePendingFrameIfNeeded())
			return true;

		for (EKey key = mKeyboard->GetFirstKey(); key != EKey::Invalid; key = mKeyboard->GetNextKey())
		{
			switch (key)
			{
			case EKey::P:
				mPaused = !mPaused;
				break;

			case EKey::O:
				mSingleStep = true;
				break;

			case EKey::R:
				mCurrentFrame = 0;
				mPendingDraw = true;
				mPresentedFrame = kInvalidFrame;
				break;

			case EKey::Escape:
				RequestQuit();
				return true;

			default:
				break;
			}
		}

		float clock_delta_time = GetClockDeltaTime();
		float world_delta_time = GetWorldDeltaTime(clock_delta_time);
		mSingleStep = false;

		if (!mHasPresentedAnyFrame)
		{
			world_delta_time = 0.0f;
			mPendingDraw = true;
		}
		else if (world_delta_time > 0.0f)
		{
			if (mCurrentFrame + 1 < mRendererPlayback->GetNumFrames())
				++mCurrentFrame;
			mPendingDraw = true;
		}

		if (mPendingDraw)
		{
			ClearDebugRenderer();
			mRendererPlayback->DrawFrame(mCurrentFrame);
			mPendingDraw = false;
		}

		if (mConfig.show_axis && mDebugRendererCleared)
			mDebugRenderer->DrawCoordinateSystem(RMat44::sIdentity());
		mDebugRendererCleared = false;

		if (!mConfig.lock_camera)
			UpdateCamera(clock_delta_time);

		if (!mRenderer->BeginFrame(mCamera, 1.0f))
			return true;

		static_cast<DebugRendererImp *>(mDebugRenderer)->DrawShadowPass();
		mRenderer->EndShadowPass();
		static_cast<DebugRendererImp *>(mDebugRenderer)->Draw();
		mRenderer->EndFrame();

		mPresentedFrame = mCurrentFrame;
		mHasPresentedAnyFrame = true;
		JPH_PROFILE_NEXTFRAME();
		return true;
	}

	float GetClockDeltaTime()
	{
		Clock::time_point now = Clock::now();
		chrono::microseconds delta = chrono::duration_cast<chrono::microseconds>(now - mLastUpdateTime);
		mLastUpdateTime = now;
		return 1.0e-6f * delta.count();
	}

	float GetWorldDeltaTime(float inClockDeltaTime)
	{
		if (mSingleStep)
			return mRequestedDeltaTime;
		if (mPaused)
		{
			mResidualDeltaTime = 0.0f;
			return 0.0f;
		}

		float world_delta_time = inClockDeltaTime + mResidualDeltaTime;
		if (world_delta_time < mRequestedDeltaTime)
		{
			mResidualDeltaTime = world_delta_time;
			return 0.0f;
		}

		mResidualDeltaTime = min(mRequestedDeltaTime, world_delta_time - mRequestedDeltaTime);
		return mRequestedDeltaTime;
	}

	void ClearDebugRenderer()
	{
		static_cast<DebugRendererImp *>(mDebugRenderer)->Clear();
		mDebugRendererCleared = true;
	}

	void UpdateCamera(float inDeltaTime)
	{
		float speed = 20.0f * inDeltaTime;
		bool shift = mKeyboard->IsKeyPressed(EKey::LShift) || mKeyboard->IsKeyPressed(EKey::RShift);
		bool control = mKeyboard->IsKeyPressed(EKey::LControl) || mKeyboard->IsKeyPressed(EKey::RControl);
		bool alt = mKeyboard->IsKeyPressed(EKey::LAlt) || mKeyboard->IsKeyPressed(EKey::RAlt);
		if (shift)
			speed *= 10.0f;
		else if (control)
			speed /= 25.0f;
		else if (alt)
			speed = 0.0f;

		Vec3 right = mCamera.mForward.Cross(mCamera.mUp);
		if (mKeyboard->IsKeyPressed(EKey::A))
			mCamera.mPos -= speed * right;
		if (mKeyboard->IsKeyPressed(EKey::D))
			mCamera.mPos += speed * right;
		if (mKeyboard->IsKeyPressed(EKey::W))
			mCamera.mPos += speed * mCamera.mForward;
		if (mKeyboard->IsKeyPressed(EKey::S))
			mCamera.mPos -= speed * mCamera.mForward;

		float heading = ATan2(mCamera.mForward.GetZ(), mCamera.mForward.GetX());
		float pitch = ATan2(mCamera.mForward.GetY(), Vec3(mCamera.mForward.GetX(), 0, mCamera.mForward.GetZ()).Length());
		heading += DegreesToRadians(mMouse->GetDX() * 0.5f);
		pitch = Clamp(pitch - DegreesToRadians(mMouse->GetDY() * 0.5f), -0.49f * JPH_PI, 0.49f * JPH_PI);
		mCamera.mForward = Vec3(Cos(pitch) * Cos(heading), Sin(pitch), Cos(pitch) * Sin(heading));
	}

	bool CapturePendingFrameIfNeeded()
	{
		if (!mConfig.export_frames || mPresentedFrame == kInvalidFrame || mPresentedFrame == mCapturedFrame)
			return false;

		fs::path out_path = mConfig.frames_out_dir / StringFormat("frame_%06u.png", mPresentedFrame).c_str();
		if (!SaveMainWindowPng(out_path))
			FatalError("Could not capture frame %u", mPresentedFrame);
		mCapturedFrame = mPresentedFrame;

		// Capture one callback after presentation because window-server snapshots race the
		// drawable commit on the same tick.
		if (mConfig.stop_after_last_frame && mCapturedFrame + 1 >= mRendererPlayback->GetNumFrames())
		{
			RequestQuit();
			return true;
		}
		return false;
	}

	void MaybeConfigureCaptureWindow()
	{
		if (!mConfig.export_frames || mCaptureWindowConfigured)
			return;
		ConfigureWindowForCapture();
		mCaptureWindowConfigured = true;
	}

	void RequestQuit()
	{
		dispatch_async(dispatch_get_main_queue(), ^{
			[NSApp terminate: nil];
		});
	}

	ViewerConfig					mConfig;
	ApplicationWindowMacOS *		mWindow = nullptr;
	Renderer *						mRenderer = nullptr;
	Font *							mFont = nullptr;
	DebugRenderer *					mDebugRenderer = nullptr;
	unique_ptr<DebugRendererPlayback> mRendererPlayback;
	KeyboardMacOS *					mKeyboard = nullptr;
	MouseMacOS *					mMouse = nullptr;
	CameraState						mCamera;
	Clock::time_point				mLastUpdateTime;
	bool							mPaused = true;
	bool							mSingleStep = false;
	bool							mPendingDraw = true;
	bool							mDebugRendererCleared = true;
	bool							mHasPresentedAnyFrame = false;
	bool							mCaptureWindowConfigured = false;
	float							mRequestedDeltaTime = 0.0f;
	float							mResidualDeltaTime = 0.0f;
	uint							mCurrentFrame = 0;
	uint							mPresentedFrame = kInvalidFrame;
	uint							mCapturedFrame = kInvalidFrame;
};

int main(int inArgC, char **inArgV)
{
	if (inArgC == 2 && string_view(inArgV[1]) == "--help")
	{
		PrintUsage(stdout);
		return 0;
	}

	optional<ViewerConfig> config = ParseArgs(inArgC, inArgV);
	if (!config.has_value())
	{
		PrintUsage(stderr);
		return 2;
	}

	RegisterDefaultAllocator();
	JPH_PROFILE_START("Main");
	FPExceptionsEnable enable_exceptions;
	JPH_UNUSED(enable_exceptions);

	{
		RecordingViewerApp app(std::move(*config));
		app.Run();
	}

	JPH_PROFILE_END();
	return 0;
}
