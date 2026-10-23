import {
  test,
  expect,
} from "../../scripts/assets/node_modules/@playwright/test";
import {
  calibrateMeasurements,
  compareCircumference,
  type MeasurementInput,
} from "../../brandme-frontend/features/spatial/fitCalibration";
const good: MeasurementInput = {
  height: [188, 188.2, 187.8],
  chest: [100, 100.5, 99.5],
  waist: [85, 85.5, 84.5],
  hip: [102, 102.2, 101.8],
  shoulder: [46, 46.5, 45.5],
  inseam: [84, 84.5, 83.5],
};
test("calibration refuses missing, nonfinite and inconsistent measurements and bounds ease without claiming fit", () => {
  const calibrated = calibrateMeasurements(good);
  expect(calibrated.valid).toBe(true);
  expect(calibrateMeasurements({ ...good, chest: [100, 103, 100] }).valid).toBe(
    false,
  );
  expect(calibrateMeasurements({ ...good, chest: [NaN, 100, 100] }).valid).toBe(
    false,
  );
  const result = compareCircumference(calibrated, "chest", {
    circumferenceCm: 108,
    uncertaintyCm: 0.5,
    source: "demo",
    revision: "fixture-v1",
  });
  expect(result.intervalCm).toEqual([6.5, 9.5]);
  expect(result.calibratedFitAvailable).toBe(false);
  expect(() =>
    compareCircumference(calibrated, "chest", {
      circumferenceCm: Infinity,
      uncertaintyCm: 0.5,
      source: "demo",
      revision: "fixture-v1",
    }),
  ).toThrow();
});
test("measurement preparation stays private, requires repeats and clears on exit while fit remains disabled", async ({
  page,
}) => {
  const uploads: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST") uploads.push(r.url());
  });
  await page.goto("/try/overshirt");
  await expect(
    page.getByRole("button", { name: /Calibrated fit/ }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Prepare measurements" }).click();
  await page
    .getByRole("button", { name: "Check measurement repeatability" })
    .click();
  await expect(page.getByText(/Height: enter three plausible/)).toBeVisible();
  const labels = {
    height: "Height",
    chest: "Chest circumference",
    waist: "Waist circumference",
    hip: "Hip circumference",
    shoulder: "Shoulder width",
    inseam: "Inseam",
  };
  for (const [key, values] of Object.entries(good))
    for (let i = 0; i < 3; i++)
      await page
        .getByLabel(`${labels[key as keyof typeof labels]} repeat ${i + 1}`, {
          exact: true,
        })
        .fill(String(values[i]));
  await page
    .getByRole("button", { name: "Check measurement repeatability" })
    .click();
  await expect(page.getByText(/Repeats are consistent/)).toBeVisible();
  await page.getByRole("button", { name: /Item image/ }).click();
  await page.getByRole("button", { name: "Prepare measurements" }).click();
  await expect(page.getByLabel("Height repeat 1", { exact: true })).toHaveValue(
    "",
  );
  expect(uploads).toEqual([]);
});
test("native device test cannot be activated in an ordinary build", async ({
  page,
}) => {
  await page.goto("/try/device-test");
  await expect(
    page.getByRole("heading", { name: "Device validation" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Begin device test" }),
  ).toHaveCount(0);
});
