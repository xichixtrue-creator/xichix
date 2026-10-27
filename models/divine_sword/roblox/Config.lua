-- Seraph Blade settings. Lives in ReplicatedStorage.SeraphBlade.Config.
-- Safe to edit: re-running the installer keeps an existing Config.

local Config = {}

Config.Colors = {
	Crystal = Color3.fromRGB(255, 252, 244), -- the white crystal blade, guard curls and grip
	Gem = Color3.fromRGB(235, 245, 255), -- the diamonds
	Gold = Color3.fromRGB(255, 200, 90), -- only used if the gold texture didn't come in with the import
	Light = Color3.fromRGB(255, 240, 205), -- the warm white light round the guard
}

-- How the white crystal looks: "Light" (glowing white Neon, the default), "Glass" (clear
-- crystal) or "Texture" (opaque, with the painted facets).
Config.CrystalStyle = "Light"
Config.CrystalTransparency = 0.08
-- How the gems look: "Glass" (clear diamond, the default), "Light" or "Texture".
Config.GemStyle = "Glass"

Config.Combat = {
	SwingCooldown = 0.4,
	ComboReset = 1.0,
	SwingDamage = { 13, 13, 20 },
	HitDelay = 0.12,
	SwingRange = 8,
	SwingWidth = 8,
	SwingHeight = 6,

	-- the special, Heaven's Verdict: a pillar of light strikes down and bursts out round you
	SpecialCooldown = 7,
	SpecialWindup = 0.35,
	SpecialDamage = 36,
	SpecialRadius = 12,

	DamageHumanoids = true, -- set false if your game handles damage itself (see SeraphHit)
	FriendlyFire = false,
}

-- Keys / buttons for the special (a touch button is added on mobile).
-- Right mouse is left out on purpose: Roblox uses it to turn the camera.
Config.SpecialInputs = { Enum.KeyCode.E, Enum.KeyCode.ButtonY }

-- Optional custom animations ("rbxassetid://123"); empty = Roblox's tool slash / lunge.
Config.Animations = {
	Swing = {},
	Special = "",
}

-- Roll of the crescent slash for each combo step (degrees). 90 = straight down.
Config.SlashAngles = { 70, -65, 95 }

Config.Sounds = {
	Equip = "rbxasset://sounds/unsheath.wav",
	Swing = "rbxasset://sounds/swordslash.wav",
	Special = "rbxasset://sounds/electronicpingshort.wav",
	Impact = "",
}

-- Paste uploaded image IDs here to override the imported textures, e.g. Sparkle = "rbxassetid://1".
-- Keys: GlowWhite GlowGold Rays Halo Ribbon RibbonGold Sparkle Mote SlashBand Trail Pillar HolyCircle
Config.Textures = {}

Config.FallbackTextures = {
	Default = "rbxasset://textures/particles/sparkles_main.dds",
}

Config.VFX = {
	IdleRange = 140, -- the moving parts of the aura only run when the camera is this close
	Aura = true, -- the white and gold energy ribbons swirling round the blade
	AuraSpeed = 0.5, -- how fast the light flows along them
	Streams = 2, -- bright streams racing along the ribbons now and then
	StreamSpeed = 0.35,
	StreamLifetime = 0.4,
	HaloPulse = true, -- the halo and light round the guard gently breathe
	ScreenFlash = true,
	CameraShake = true,
	SlashRadius = 5,
	SlashWidth = 1.2,
	VerdictRadius = 11, -- size of Heaven's Verdict's ring and holy circle
}

return Config
